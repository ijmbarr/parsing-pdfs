from __future__ import division

import math
import pdfminer
from collections import defaultdict


from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter

from pdfminer.layout import LAParams
from pdfminer.converter import PDFPageAggregator

TEXT_ELEMENTS = [
    pdfminer.layout.LTTextBox,
    pdfminer.layout.LTTextBoxHorizontal,
    pdfminer.layout.LTTextLine,
    pdfminer.layout.LTTextLineHorizontal
]


def extract_layout_by_page(pdf_path):
    """
    Extracts the layouts of the pages of a PDF document
    specified by pdf_path.

    Uses the PDFminer library. See its documentation for
    details of the objects returned.

    See:
    - https://euske.github.io/pdfminer/programming.html
    - http://denis.papathanasiou.org/posts/2010.08.04.post.html
    """
    laparams = LAParams()

    fp = open(pdf_path, 'rb')
    parser = PDFParser(fp)
    document = PDFDocument(parser)

    if not document.is_extractable:
        raise PDFTextExtractionNotAllowed

    rsrcmgr = PDFResourceManager()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)

    layouts = []
    for page in PDFPage.create_pages(document):
        interpreter.process_page(page)
        layouts.append(device.get_result())

    return layouts


def get_tables(pdf_path):
    """
    Tried to extract tabular information from the document in pdf_path.
    :param pdf_path: pdf document path
    :return: List of pages, each page is a list of lists
    """
    return [page_to_table(page_layout) for page_layout in
            extract_layout_by_page(pdf_path)]


def page_to_table(page_layout):
    """
    Given a pdfminer page object, tries to convert it to a table
    :param page_layout
    :return: list of lists
    """
    texts = []
    rects = []
    other = []

    for e in page_layout:
        if isinstance(e, pdfminer.layout.LTTextBoxHorizontal):
            texts.append(e)
        elif isinstance(e, pdfminer.layout.LTRect):
            rects.append(e)
        else:
            other.append(e)

    # convert text elements to characters
    # and rectangles to lines
    characters = extract_characters(texts)
    lines = [cast_as_line(r) for r in rects
             if width(r) < 2 and
             area(r) > 1]

    # match each character to a bounding rectangle where possible
    box_char_dict = {}
    for c in characters:
        # choose the bounding box that occurs the majority of times for each of these:
        bboxes = defaultdict(int)
        l_x, l_y = c.bbox[0], c.bbox[1]
        bbox_l = find_bounding_rectangle((l_x, l_y), lines)
        bboxes[bbox_l] += 1

        c_x, c_y = math.floor((c.bbox[0] + c.bbox[2]) / 2), math.floor((c.bbox[1] + c.bbox[3]) / 2)
        bbox_c = find_bounding_rectangle((c_x, c_y), lines)
        bboxes[bbox_c] += 1

        u_x, u_y = c.bbox[2], c.bbox[3]
        bbox_u = find_bounding_rectangle((u_x, u_y), lines)
        bboxes[bbox_u] += 1

        # if all values are in different boxes, default to character center.
        # otherwise choose the majority.
        if max(bboxes.values()) == 1:
            bbox = bbox_c
        else:
            bbox = max(bboxes.items(), key=lambda x: x[1])[0]

        if bbox is None:
            continue

        if bbox in box_char_dict.keys():
            box_char_dict[bbox].append(c)
            continue

        box_char_dict[bbox] = [c]

    # look for empty bounding boxes by scanning
    # over a grid of values on the page
    for x in range(100, 550, 10):
        for y in range(50, 800, 10):
            bbox = find_bounding_rectangle((x, y), lines)

            if bbox is None:
                continue

            if bbox in box_char_dict.keys():
                continue

            box_char_dict[bbox] = []

    return boxes_to_table(box_char_dict)


def flatten(lst):
    """
    Flatterns a list of lists one level.
    :param lst: list of lists
    :return: list
    """
    return [subelem for elem in lst for subelem in elem]


def extract_characters(element):
    if isinstance(element, pdfminer.layout.LTChar):
        return [element]

    if any(isinstance(element, i) for i in TEXT_ELEMENTS):
        elements = []
        for e in element:
            elements += extract_characters(e)
        return elements

    if isinstance(element, list):
        return flatten([extract_characters(l) for l in element])

    return []


def width(rect):
    x0, y0, x1, y1 = rect.bbox
    return min(x1 - x0, y1 - y0)


def length(rect):
    x0, y0, x1, y1 = rect.bbox
    return max(x1 - x0, y1 - y0)


def area(rect):
    x0, y0, x1, y1 = rect.bbox
    return (x1 - x0) * (y1 - y0)


def cast_as_line(rect):
    x0, y0, x1, y1 = rect.bbox

    if x1 - x0 > y1 - y0:
        return (x0, y0, x1, y0, "H")
    else:
        return (x0, y0, x0, y1, "V")


def does_it_intersect(x, (xmin, xmax)):
    return (x <= xmax and x >= xmin)


def find_bounding_rectangle((x, y), lines):
    v_intersects = [l for l in lines
                    if l[4] == "V"
                    and does_it_intersect(y, (l[1], l[3]))]

    h_intersects = [l for l in lines
                    if l[4] == "H"
                    and does_it_intersect(x, (l[0], l[2]))]

    if len(v_intersects) < 2 or len(h_intersects) < 2:
        return None

    v_left = [v[0] for v in v_intersects
              if v[0] < x]

    v_right = [v[0] for v in v_intersects
               if v[0] > x]

    if len(v_left) == 0 or len(v_right) == 0:
        return None

    x0, x1 = max(v_left), min(v_right)

    h_down = [h[1] for h in h_intersects
              if h[1] < y]

    h_up = [h[1] for h in h_intersects
            if h[1] > y]

    if len(h_down) == 0 or len(h_up) == 0:
        return None

    y0, y1 = max(h_down), min(h_up)

    return (x0, y0, x1, y1)


def chars_to_string(chars):
    if not chars:
        return ""
    rows = sorted(list(set(c.bbox[1] for c in chars)), reverse=True)
    text = ""
    for row in rows:
        sorted_row = sorted([c for c in chars if c.bbox[1] == row], key=lambda c: c.bbox[0])
        text += "".join(c.get_text() for c in sorted_row)
    return text


def boxes_to_table(box_record_dict):
    boxes = box_record_dict.keys()
    rows = sorted(list(set(b[1] for b in boxes)), reverse=True)
    table = []
    for row in rows:
        sorted_row = sorted([b for b in boxes if b[1] == row], key=lambda b: b[0])
        table.append([chars_to_string(box_record_dict[b]) for b in sorted_row])
    return table
