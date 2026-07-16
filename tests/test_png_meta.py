"""Pure-Python PNG metadata reading and RGBA writing."""

import struct
import zlib

import pytest

from reblend.project.png_meta import PngError, read_png_meta, write_rgba_png


def test_write_read_roundtrip(tmp_path):
    path = tmp_path / "sheet.png"
    write_rgba_png(path, 65, 130, bytes(65 * 130 * 4))
    meta = read_png_meta(path)
    assert (meta.width, meta.height) == (65, 130)
    assert meta.bit_depth == 8
    assert meta.color_type == 6
    assert meta.is_8bit_rgba


def test_written_file_decodes_with_zlib(tmp_path):
    # The IDAT payload must inflate to height * (1 + width*4) filter-prefixed rows.
    path = tmp_path / "tiny.png"
    pixels = bytes(range(4)) * 4  # 2x2 RGBA
    write_rgba_png(path, 2, 2, pixels)
    blob = path.read_bytes()
    idat_start = blob.index(b"IDAT") + 4
    length = struct.unpack(">I", blob[idat_start - 8 : idat_start - 4])[0]
    raw = zlib.decompress(blob[idat_start : idat_start + length])
    assert len(raw) == 2 * (1 + 2 * 4)
    assert raw[0] == 0 and raw[9] == 0  # filter type 0 per row


def test_pixel_length_mismatch_raises(tmp_path):
    with pytest.raises(ValueError, match="bytes"):
        write_rgba_png(tmp_path / "x.png", 2, 2, bytes(3))


def test_not_a_png_raises(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"definitely not a png")
    with pytest.raises(PngError, match="not a PNG"):
        read_png_meta(bad)


def test_missing_file_raises(tmp_path):
    with pytest.raises(PngError, match="cannot read"):
        read_png_meta(tmp_path / "absent.png")
