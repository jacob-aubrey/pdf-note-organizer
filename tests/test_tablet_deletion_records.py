"""Erased CRDT runs must never resurrect marks in generated reading PDFs."""
from dataclasses import replace
from io import BytesIO
import unittest

import pymupdf
from rmscene import read_blocks, write_blocks
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import SceneLineItemBlock, SceneTombstoneItemBlock, SceneTextItemBlock
from rmscene.tagged_block_common import CrdtId

from note_organizer.remarkable_pdf import annotated_pdf, scene, UnsupportedAnnotations
from tests.test_remarkable import fixture


class TabletDeletionTests(unittest.TestCase):
    def fixture(self, *, length=1, before=False, group=False):
        item, bundle = fixture()
        name = next(k for k in bundle if k.endswith(".rm"))
        blocks = list(read_blocks(BytesIO(bundle[name])))
        line = next(b for b in blocks if isinstance(b, SceneLineItemBlock))
        extra = replace(line, item=replace(line.item, item_id=CrdtId(1, 102), left_id=line.item.item_id))
        surviving = replace(line, item=replace(line.item, item_id=CrdtId(2, 101), left_id=CrdtId(1, 102)))
        blocks.extend([extra, surviving])
        target = line
        if group:
            from rmscene.scene_stream import SceneGroupItemBlock
            target = next(b for b in blocks if isinstance(b, SceneGroupItemBlock))
        tombstone = SceneTombstoneItemBlock(target.parent_id, replace(target.item, deleted_length=length, value=None))
        blocks.insert(0, tombstone) if before else blocks.append(tombstone)
        stream = BytesIO()
        write_blocks(stream, blocks, options={"version": "3.1"})
        bundle[name] = stream.getvalue()
        return item, bundle

    def test_single_deleted_ink_is_absent_but_other_marks_survive(self):
        item, bundle = self.fixture()
        with pymupdf.open(stream=annotated_pdf(item, bundle), filetype="pdf") as doc:
            kinds = [a.type[1] for a in doc[0].annots()]
        self.assertEqual(kinds.count("Ink"), 2)
        self.assertEqual(kinds.count("Highlight"), 1)

    def test_compressed_deletion_removes_whole_run_only_for_its_author(self):
        item, bundle = self.fixture(length=2)
        with pymupdf.open(stream=annotated_pdf(item, bundle), filetype="pdf") as doc:
            self.assertEqual(sum(a.type[1] == "Ink" for a in doc[0].annots()), 1)

    def test_deletion_before_original_block_still_wins(self):
        item, bundle = self.fixture(length=2, before=True)
        with pymupdf.open(stream=annotated_pdf(item, bundle), filetype="pdf") as doc:
            self.assertEqual(sum(a.type[1] == "Ink" for a in doc[0].annots()), 1)

    def test_deleted_group_never_exposes_its_children(self):
        item, bundle = self.fixture(group=True)
        with pymupdf.open(stream=annotated_pdf(item, bundle), filetype="pdf") as doc:
            # Root text is separate from the erased drawing group.
            self.assertEqual([a.type[1] for a in doc[0].annots()], ["Text"])
            self.assertEqual(next(doc[0].annots()).info["content"], "Typed margin note")

    def test_unknown_text_items_and_malformed_tombstones_still_fail_closed(self):
        item, bundle = fixture()
        name = next(k for k in bundle if k.endswith(".rm"))
        blocks = list(read_blocks(BytesIO(bundle[name])))
        line = next(b for b in blocks if isinstance(b, SceneLineItemBlock))
        for block in (SceneTextItemBlock(line.parent_id, replace(line.item, value=None)),
                      SceneTombstoneItemBlock(line.parent_id, replace(line.item, value=None, deleted_length=0)),
                      SceneTombstoneItemBlock(line.parent_id, replace(line.item, value=None, deleted_length=100_001))):
            stream = BytesIO()
            write_blocks(stream, [*blocks, block], options={"version": "3.1"})
            with self.assertRaises(UnsupportedAnnotations):
                scene(stream.getvalue())
