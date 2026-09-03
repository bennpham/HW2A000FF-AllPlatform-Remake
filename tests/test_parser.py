"""The ported parser must keep the original's behaviour, quirks included."""

from __future__ import annotations

from hw2a000ff.nimble import XmlFile, XmlTag
from hw2a000ff.nimble.parser import parse_attributes
from hw2a000ff.nimble.reader import CharReader


def parse(text: str) -> XmlTag:
    return XmlFile.from_text(text).document_element


def test_reads_attributes_quoted_unquoted_and_valueless():
    root = parse('<tag a="one" b=two c d="four" />')
    assert root.attributes == {"a": "one", "b": "two", "c": "", "d": "four"}


def test_decodes_html_entities_in_attributes():
    root = parse('<tag text="a &amp; b &lt;c&gt; &quot;d&quot;" />')
    assert root.attributes["text"] == 'a & b <c> "d"'


def test_duplicate_attribute_keeps_the_last_and_warns():
    warnings: list[str] = []
    xml = XmlFile.from_text('<tag a="1" a="2" />', warn=warnings.append)
    assert xml.document_element.attributes["a"] == "2"
    assert any("duplicate" in w for w in warnings)


def test_nested_tags_and_values():
    root = parse("<a><b>one</b><c><d>two</d></c></a>")
    assert root.find_tag_by_name("b").value == "one"
    assert root.find_tag_by_name("d").value == "two"


def test_find_tag_by_name_searches_direct_children_first():
    root = parse("<a><x><t>deep</t></x><t>shallow</t></a>")
    assert root.find_tag_by_name("t").value == "shallow"


def test_query_indexer_matches_name_and_attribute():
    root = parse('<a><entry name="hp"><int>100</int></entry>'
                 '<entry name="mp"><int>50</int></entry></a>')
    assert root["entry[name=hp]"].find_tag_by_name("int").value == "100"
    assert root["entry[name=mp]"].find_tag_by_name("int").value == "50"
    assert root["entry[name=nope]"] is None


def test_chained_query_helpers_short_circuit():
    root = parse('<a><entry name="hp"><int>100</int></entry></a>')
    assert root.qv("entry[name=hp]", "int") == "100"
    assert root.qv("entry[name=missing]", "int") == ""
    assert root.q("entry[name=missing]", "int") is None


def test_comments_are_marked_and_excluded_from_elements():
    root = parse("<a><!-- note --><b/></a>")
    assert [c.is_comment for c in root.children] == [True, False]
    assert [c.name for c in root.elements()] == ["b"]


def test_indentation_becomes_a_text_node_as_in_the_original():
    # The parser trims \r \n \t but never spaces, so indented XML carries text
    # nodes. Downstream code uses elements()/first_element() because of it.
    root = parse("<a>\n  <b>1</b>\n</a>")
    assert any(c.is_text_node for c in root.children)
    assert root.first_element().name == "b"


def test_first_element_skips_whitespace_and_comments():
    root = parse("<a>\n  <!-- c -->\n  <b>1</b>\n</a>")
    assert root.first_element().name == "b"
    assert root.element_value() == "1"


def test_self_closing_tag_consumes_its_bracket():
    # Guards the Debug.Assert(fs.Expect('>')) that a release build strips out,
    # which leaves a stray '>' in the stream.
    root = parse('<a><b x="1"/><c>text</c></a>')
    assert [t.name for t in root.elements()] == ["b", "c"]
    assert root.find_tag_by_name("c").value == "text"


def test_declaration_is_parsed_separately():
    xml = XmlFile.from_text('<?xml version="1.0" encoding="UTF-8"?><a/>')
    assert xml.declaration.attributes == {"version": "1.0", "encoding": "UTF-8"}
    assert xml.document_element.name == "a"


def test_reader_read_until_and_expect():
    reader = CharReader("abc>rest")
    text, terminator = reader.read_until(">")
    assert (text, terminator) == ("abc", ">")
    assert reader.expect("rest")


def test_reader_pads_past_end_of_stream():
    reader = CharReader("ab")
    assert reader.read_string(4) == "ab\0\0"
    assert reader.end_of_stream


def test_parse_attributes_reports_open_tag():
    result = parse_attributes(CharReader('a="1">'))
    assert result.open_tag is True
    assert result.attributes == {"a": "1"}
