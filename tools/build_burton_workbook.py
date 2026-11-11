#!/usr/bin/env python3
# Build the Burton Inn negotiation workbook (burton-inn/workbook.md) as a PDF
# and an editable Word file, in the house document style. The workbook lists
# the lease terms to agree or discuss; agreed terms then go into Section 1/3.

from build_burton_lease import BDIR, version_of, check_glyphs, build
import build_lease_docs as house
from docx import Document
from build_burton_docx import emit, style_document

if __name__ == '__main__':
    with open(BDIR + '/workbook.md') as f:
        md = f.read()
    check_glyphs(md)
    ver = version_of(md)
    build(house.md_to_story(md), BDIR + '/workbook.pdf',
          'The Burton Inn — Lease Workbook',
          f'The Burton Inn — Lease Workbook    {ver}')
    doc = Document()
    style_document(doc)
    emit(doc, md, first=True)
    doc.save(BDIR + '/workbook.docx')
    print('wrote', BDIR + '/workbook.docx')
