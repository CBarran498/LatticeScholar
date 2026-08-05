from latticescholar.services.importer import import_bibliography


def test_import_bibtex_and_ris_records():
    bib = b"""@article{demo, title={Evidence from Scholar}, author={Ada Lovelace and Grace Hopper}, year={2025}, journal={Journal One}, doi={10.1/demo}, abstract={Useful evidence}}"""
    papers = import_bibliography("scholar.bib", bib, "Google Scholar")
    assert papers[0].title == "Evidence from Scholar"
    assert papers[0].authors == ["Ada Lovelace", "Grace Hopper"]
    assert papers[0].sources == ["Google Scholar"]

    ris = b"""TY  - JOUR
TI  - Chinese research record
AU  - Zhang San
PY  - 2024
JO  - Journal Two
DO  - 10.2/example
AB  - Imported abstract
ER  -
"""
    papers = import_bibliography("cnki.enw", ris, "中国知网")
    assert papers[0].year == 2024
    assert papers[0].venue == "Journal Two"
    assert papers[0].sources == ["中国知网"]
