"""Synthetic PDF fixtures adapted from the original sorter diagnostics."""
def verify_patent_support(folder):
    """Round-trip synthetic patent pages through PDF extraction and naming."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from note_organizer.sorting.core_logic import get_basic_document_details, build_proposed_filename
    fixtures = (
        ("Patent", "Patent No.: US 9,123,456 B2", "(45) Date of Patent: Sep. 1, 2015", "Li_et_al_US_Patent_2015_US9123456B2.pdf"),
        ("Patent Application Publication", "Pub. No.: US 2014/0123456 A1", "(43) Pub. Date: May 1, 2014", "Li_et_al_US_Patent_Application_2014_US20140123456A1.pdf"),
    )
    for index, (kind, number, published, expected) in enumerate(fixtures):
        lines = ["SYNTHETIC TEST DATA", "(12) United States " + kind,
                 "(10) " + number, published, "(54) TEST DEVICE",
                 "(72) Inventors: Wei Li, Boston (US); Jane Smith, Boston (US); Alex Jones, Boston (US)",
                 "(73) Assignee: Example Company", "(22) Filed: Jan. 1, 2009"]
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 9 Tf 30 750 Td 18 TL\n" + "\n".join(f"({line}) Tj T*" for line in escaped) + "\nET").encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        path = folder / f"synthetic-patent-{index}.pdf"
        writer.write(path)
        details = get_basic_document_details(path)
        assert build_proposed_filename(details, ".pdf") == expected
        assert not details["needs_review"]
    return details


def synthetic_cff_font_pdf():
    """The original sorter's 1,169-byte synthetic embedded-font PDF."""
    import base64
    from io import BytesIO
    return BytesIO(base64.b64decode(
        'JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAv'
        'UGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdl'
        'cyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Ci9Gb250IDw8Ci9GMSA3IDAg'
        'Ugo+Pgo+PgovTWVkaWFCb3ggWyAwLjAgMC4wIDEwMCAxMDAgXQovUGFyZW50IDIgMCBSCi9Db250ZW50cyA4IDAgUgo+Pgpl'
        'bmRvYmoKNSAwIG9iago8PAovU3VidHlwZSAvVHlwZTFDCi9MZW5ndGggMTExCj4+CnN0cmVhbQoBAAQBAAEBARNQYXBlclNv'
        'cnRlckZpeHR1cmUAAQEBG/gbAvgbA/gYBL2L+Lr5UAXdD+AQi/cDEuMRAAEBARJQYXBlciBTb3J0ZXIgVGVzdAAAAAAiAAEh'
        'AAIBAQQS+OwO+Oy9FveO+VD3jv1QBQ4KZW5kc3RyZWFtCmVuZG9iago2IDAgb2JqCjw8Ci9UeXBlIC9Gb250RGVzY3JpcHRv'
        'cgovRm9udE5hbWUgL1BhcGVyU29ydGVyRml4dHVyZQovRmxhZ3MgMzIKL0ZvbnRCQm94IFsgMCAwIDYwMCA3MDAgXQovSXRh'
        'bGljQW5nbGUgMAovQXNjZW50IDcwMAovRGVzY2VudCAwCi9DYXBIZWlnaHQgNzAwCi9TdGVtViA4MAovRm9udEZpbGUzIDUg'
        'MCBSCj4+CmVuZG9iago3IDAgb2JqCjw8Ci9UeXBlIC9Gb250Ci9TdWJ0eXBlIC9UeXBlMQovQmFzZUZvbnQgL1BhcGVyU29y'
        'dGVyRml4dHVyZQovRmlyc3RDaGFyIDMzCi9MYXN0Q2hhciAzMwovV2lkdGhzIFsgNjAwIF0KL0VuY29kaW5nIC9XaW5BbnNp'
        'RW5jb2RpbmcKL0ZvbnREZXNjcmlwdG9yIDYgMCBSCj4+CmVuZG9iago4IDAgb2JqCjw8Ci9MZW5ndGggMzEKPj4Kc3RyZWFt'
        'CkJUIC9GMSAxMiBUZiAxMCAzMCBUZCAoISkgVGogRVQKZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgOQowMDAwMDAwMDAwIDY1'
        'NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA1NCAwMDAwMCBuIAowMDAwMDAwMTEzIDAwMDAwIG4gCjAwMDAw'
        'MDAxNjIgMDAwMDAgbiAKMDAwMDAwMDI5NCAwMDAwMCBuIAowMDAwMDAwNDczIDAwMDAwIG4gCjAwMDAwMDA2NjIgMDAwMDAg'
        'biAKMDAwMDAwMDgzMyAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDkKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKPj4Kc3Rh'
        'cnR4cmVmCjkxNAolJUVPRgo='
    ))
