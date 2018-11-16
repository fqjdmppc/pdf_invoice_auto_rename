from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTFigure, LTImage, LTTextBoxHorizontal, LTChar
from pdfminer.pdfpage import PDFPage
import re
import os
def with_pdf (pdf_doc, pdf_pwd, fn, *args):
    result = None
    try:
    # open the pdf file
        fp = open(pdf_doc, 'rb')
        # create a parser object associated with the file object
        parser = PDFParser(fp)
        # create a PDFDocument object that stores the document structure
        doc = PDFDocument(parser, pdf_pwd)
        # connect the parser and document objects
        parser.set_document(doc)

        if doc.is_extractable:
            # apply the function and return the result
            result = fn(doc, *args)
        # close the pdf file
        fp.close()
    except IOError:
        # the file doesn't exist or similar problem
        pass
    return result

# def _parse_toc (doc):
#     """With an open PDFDocument object, get the table of contents (toc) data
#     [this is a higher-order function to be passed to with_pdf()]"""
#     toc = []
#     try:
#         outlines = doc.get_outlines()

#         for (level,title,dest,a,se) in outlines:
#             toc.append( (level, title) )
#     except PDFNoOutlines:
#         print("nooutlines")
#         pass
#     return toc

# def get_toc (pdf_doc, pdf_pwd=''):
#     return with_pdf(pdf_doc, pdf_pwd, _parse_toc)

def _parse_pages (doc, images_folder):
    rsrcmgr = PDFResourceManager()
    laparams = LAParams()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    text_content = [] # a list of strings, each representing text collected from each page of the doc
    for i, page in enumerate(PDFPage.create_pages(doc)):
        interpreter.process_page(page)
        # receive the LTPage object for this page
        layout = device.get_result()
        # layout is an LTPage object which may contain child objects like LTTextBox, LTFigure, LTImage, etc.
        text_content.append(parse_lt_objs(layout._objs, (i+1), images_folder))
    return text_content

# def get_pages (pdf_doc, pdf_pwd='', images_folder='/tmp'):
# """Process each of the pages in this pdf file and print the entire text to stdout"""
#     print('\n\n'.join(with_pdf(pdf_doc, pdf_pwd, _parse_pages, *tuple([images_folder]))))

def get_pages (pdf_doc, pdf_pwd='', images_folder='/tmp'):
    return with_pdf(pdf_doc, pdf_pwd, _parse_pages, *tuple([images_folder]))

# return string if LTFigure contains all char, None for normal LTFigure
def is_LTFigure_string(lt_objs):
    ret = ''
    for lt_obj in lt_objs:
        if not isinstance(lt_obj, LTChar):
            return None
        else:
            ret += lt_obj.get_text()
    return ret

def get_str(lt_obj):
    if isinstance(lt_obj, LTFigure):
        return is_LTFigure_string(lt_obj)
    else:
        return lt_obj.get_text()

def parse_lt_objs (lt_objs, page_number, images_folder, ret=[]):
    for lt_obj in lt_objs:
        if isinstance(lt_obj, LTTextBox) or isinstance(lt_obj, LTTextLine) or isinstance(lt_obj, LTTextBoxHorizontal):
            # text
            # text_content.append(lt_obj.get_text())
            # print(lt_obj)
            ret.append(lt_obj)
    #     elif isinstance(lt_obj, LTImage):
    #         # an image, so save it to the designated folder, and note it's place in the text
    #         saved_file = save_image(lt_obj, page_number, images_folder)
    #         if saved_file:
    #             # use html style <img /> tag to mark the position of the image within the text
    #             text_content.append('<img src="'+os.path.join(images_folder, saved_file)+'" />')
    #         else:
    #             print >> sys.stderr, "Error saving image on page", page_number, lt_obj.__repr__
        elif isinstance(lt_obj, LTFigure):
            char_figure = is_LTFigure_string(lt_obj)
            # LTFigure objects are containers for other LT* objects, so recurse through the children
            if char_figure is not None:
                ret.append(lt_obj)
            else:
                parse_lt_objs(lt_obj._objs, page_number, images_folder, ret)

def within_bbox(bbox, x, y):
    return bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]

def split_multi_line(obj):
    #ret type: (list of each line str, min y, line height)
    x = get_str(obj).split('\n')
    while (x and x[-1] == ''):
        x = x[:-1]
    x.reverse()
    return (x, obj.y0, (obj.y1 - obj.y0) / max(1, len(x)))

def find_target_str_y(objs, bbox, target_str):
    target_y = -1
    target_height = -1
    for _ in objs:
        if target_y >= 0: 
            break
        splitted, min_y, line_height = split_multi_line(_)
        for j in range(len(splitted)):
            if within_bbox(bbox, _.x0, min_y + j * line_height) and re.search(target_str, re.sub('\\s', '', splitted[j])):
                target_y = min_y + j * line_height
                target_height = line_height
                break
    return target_y, target_height

def search_cat_str(objs, bbox, target_y, target_height):
    all_str = []
    bbox2 = (-0xffff, target_y - target_height / 2, 0xffff, target_y + target_height)
    for _ in objs:
        splitted, min_y, line_height = split_multi_line(_)
        for j in range(len(splitted)):
            if within_bbox(bbox, _.x0, min_y + j * line_height) and within_bbox(bbox2, 0, min_y + j * line_height):
                all_str.append((splitted[j], _.x0))
    
    sorted(all_str, key=lambda _: _[-1])
    ret = ''
    for _ in all_str:
        ret += _[0]

    return re.sub('\\s', '', re.sub('：', ':', ret))

def get_keyword(objs, bbox, keyword):
    target_y, target_height = find_target_str_y(objs, bbox, keyword)
    can_not_found_ret = 'NoName'
    if target_y < 0: 
        return can_not_found_ret
    else:
        return search_cat_str(objs, bbox, target_y, target_height).split(':')[-1]

    return can_not_found_ret

def build_name(pdf_path):
    fp = open(pdf_path, 'rb')
    # create a parser object associated with the file object
    parser = PDFParser(fp)
    # create a PDFDocument object that stores the document structure
    doc = PDFDocument(parser, '')
    # connect the parser and document objects
    parser.set_document(doc)
    rsrcmgr = PDFResourceManager()
    laparams = LAParams()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    pages = []
    for page in PDFPage.create_pages(doc):
        interpreter.process_page(page)
        # receive the LTPage object for this page
        layout = device.get_result()
        # layout is an LTPage object which may contain child objects like LTTextBox, LTFigure, LTImage, etc.
        # text_content.append(parse_lt_objs(layout._objs, (i+1), images_folder))
        pages.append(layout)


    max_x = pages[0].x1
    max_y = pages[0].y1
    seller_name_bbox = (0, 0, max_x / 3, max_y / 3)
    invoice_number_bbox = (max_x * 2 / 3, max_y * 2 / 3, max_x, max_y)
    amount_bbox = (max_x * 2 / 3, 0, max_x, max_y / 3)
    ret = []
    parse_lt_objs(pages[0], 1, '', ret)

    fp.close()
    return '%s-%s.pdf' % (get_keyword(ret, seller_name_bbox, "名称"), get_keyword(ret, invoice_number_bbox, "发票号码"))
    # return '%s-%s.pdf' % (get_keyword(ret, amount_bbox, "小写"), get_keyword(ret, invoice_number_bbox, "发票号码"))


dirpath, dirname, filenames = list(os.walk('Your folder'))[0]
for _ in filenames:
    if re.search('[^A-Za-z0-9_\\-.]', _) is None:
        new_name = build_name(dirpath + '\\' + _)
        print(new_name)
        os.rename(dirpath + '\\' + _, dirpath + '\\' + new_name)
