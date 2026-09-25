"""安全距离检查（trim-safety）算法单元测试。"""
import pytest

from app.imposition import trim_safety


def _check(page_contents, *, trim_margin_mm=5.0, fold_margin_mm=8.0, **overrides):
    """默认 4 页 1 张、左装订、页宽/页高 100、无中缝、long 翻转。"""
    params = {
        "total_pages": 4,
        "max_sheets": 1,
        "binding": "left",
        "page_width_mm": 100.0,
        "page_height_mm": 100.0,
        "gutter_mm": 0.0,
        "duplex_flip": "long",
        "trim_margin_mm": trim_margin_mm,
        "fold_margin_mm": fold_margin_mm,
        "page_contents": page_contents,
    }
    params.update(overrides)
    return trim_safety(**params)


def test_response_echoes_layout_and_margins():
    result = _check([], trim_margin_mm=3.0, fold_margin_mm=6.0, gutter_mm=20.0)
    assert result["paper_width_mm"] == 220.0
    assert result["paper_height_mm"] == 100.0
    assert result["trim_margin_mm"] == 3.0
    assert result["fold_margin_mm"] == 6.0
    assert result["violation_count"] == 0
    assert result["violations"] == []


def test_safe_rectangles_produce_no_violations():
    # 第 4 页（正面左槽 x=0）：四周均留足 10 mm，安全距离 5/8 全部满足
    result = _check([(4, [(10, 10, 20, 20)])])
    assert result["violation_count"] == 0
    assert result["violations"] == []


def test_outer_edge_uses_trim_margin():
    # 第 4 页正面左槽：页内 (0,10,20,20) -> 纸面 x 0..20，外缘（左边）距离 0 < 5
    result = _check([(4, [(0, 10, 20, 20)])])
    assert result["violations"] == [
        {
            "signature_index": 1,
            "sheet_index": 1,
            "side": "front",
            "page": 4,
            "edge": "left",
            "rect": {"x_mm": 0.0, "y_mm": 10.0, "width_mm": 20.0, "height_mm": 20.0},
        }
    ]


def test_gutter_side_uses_fold_margin_for_left_slot():
    # 左槽中缝侧为右边：页内 (80,10,20,20) -> 纸面 80..100，右边距离 0 < 折缝 8；
    # 折缝 8 > 外裁 5，同一矩形若按外裁检查本不会越线
    result = _check([(4, [(80, 10, 20, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["right"]
    assert result["violations"][0]["rect"]["x_mm"] == 80.0
    # 距离 6 mm：小于折缝 8 仍越线
    result = _check([(4, [(74, 10, 20, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["right"]
    # 距离恰好 8 mm（贴安全线）视为合格
    result = _check([(4, [(72, 10, 20, 20)])])
    assert result["violations"] == []


def test_gutter_side_uses_fold_margin_for_right_slot():
    # 第 1 页正面右槽（x=100）：中缝侧为左边；页内 (0,10,20,20) -> 纸面 100..120，
    # 左边距离 0 < 折缝 8
    result = _check([(1, [(0, 10, 20, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["left"]
    assert result["violations"][0]["page"] == 1
    assert result["violations"][0]["rect"]["x_mm"] == 100.0
    # 页内 (92,10,8,20) -> 纸面 192..200，外缘（右边）距离 0 < 外裁 5
    result = _check([(1, [(92, 10, 8, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["right"]


def test_top_and_bottom_use_trim_margin():
    # 第 4 页左槽：页内 (10,0,20,20) 顶边距离 0 < 5 -> top；
    # 页内 (10,80,20,20) 底边距离 0 < 5 -> bottom
    result = _check([(4, [(10, 0, 20, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["top"]
    result = _check([(4, [(10, 80, 20, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["bottom"]


def test_touching_safety_line_counts_as_pass():
    # 各边距离恰好等于安全距离（贴安全线）全部合格
    # 左槽：左 5、右（中缝侧）8、上 5、下 5 -> 页内 (5,5,87,90)
    result = _check([(4, [(5, 5, 87, 90)])])
    assert result["violations"] == []
    # 右槽（第 1 页，x=100）：左（中缝侧）8、右 5 -> 页内 (8,5,87,90)
    result = _check([(1, [(8, 5, 87, 90)])])
    assert result["violations"] == []


def test_zero_margins_allow_edge_to_edge_rectangles():
    # 安全距离为 0：矩形贴满整页也合格
    result = _check(
        [(4, [(0, 0, 100, 100)])],
        trim_margin_mm=0.0,
        fold_margin_mm=0.0,
    )
    assert result["violations"] == []


def test_one_rectangle_can_violate_multiple_edges_in_order():
    # 页内 (0,0,20,20) 在左槽：左（0<5）与上（0<5）同时越线，按边序 左->上 返回
    result = _check([(4, [(0, 0, 20, 20)])])
    assert [v["edge"] for v in result["violations"]] == ["left", "top"]
    for violation in result["violations"]:
        assert violation["rect"] == {
            "x_mm": 0.0,
            "y_mm": 0.0,
            "width_mm": 20.0,
            "height_mm": 20.0,
        }
        assert violation["page"] == 4
        assert violation["side"] == "front"


def test_long_flip_back_uses_swapped_slots():
    # long 背面交换槽位：背右 = 第 2 页（x=100），中缝侧为左边
    # 页内 (0,0,10,10) -> 纸面 100..110 / 0..10：左 0 < 折缝 8、上 0 < 外裁 5
    result = _check([(2, [(0, 0, 10, 10)])])
    assert [
        (v["side"], v["page"], v["edge"]) for v in result["violations"]
    ] == [("back", 2, "left"), ("back", 2, "top")]
    assert result["violations"][0]["rect"]["x_mm"] == 100.0


def test_short_flip_back_rotates_180():
    # short 背面保持槽位：背左 = 第 2 页（x=0）旋转 180
    # 页内 (0,0,10,10) -> 纸面 x: 100-0-10=90..100，y: 100-0-10=90..100
    # 左槽中缝侧（右）距离 0 < 8、底边距离 0 < 5
    result = _check([(2, [(0, 0, 10, 10)])], duplex_flip="short")
    assert [
        (v["side"], v["page"], v["edge"]) for v in result["violations"]
    ] == [("back", 2, "right"), ("back", 2, "bottom")]
    assert result["violations"][0]["rect"] == {
        "x_mm": 90.0,
        "y_mm": 90.0,
        "width_mm": 10.0,
        "height_mm": 10.0,
    }


def test_right_binding_page_order_reused():
    # 右装订正面：左 = 第 1 页（x=0）、右 = 第 4 页（x=100）
    # 第 1 页在左槽：页内 (0,10,20,20) -> 外缘（左）距离 0 < 5
    result = _check([(1, [(0, 10, 20, 20)])], binding="right")
    assert [(v["page"], v["edge"]) for v in result["violations"]] == [(1, "left")]


def test_gutter_width_shifts_right_slot():
    # 中缝 20、纸面 220：右槽 x=120；第 1 页页内 (0,10,20,20) -> 纸面 120..140，
    # 中缝侧（左）距离 0 < 折缝 8
    result = _check([(1, [(0, 10, 20, 20)])], gutter_mm=20.0)
    assert result["paper_width_mm"] == 220.0
    assert [v["edge"] for v in result["violations"]] == ["left"]
    assert result["violations"][0]["rect"]["x_mm"] == 120.0


def test_blank_slots_and_pages_without_content_are_skipped():
    # 1 页补 3 空白：正面 (null, 1)、背面 (null, null)；只检查第 1 页
    result = _check([(1, [(0, 0, 10, 10)])], total_pages=1)
    assert [(v["side"], v["page"], v["edge"]) for v in result["violations"]] == [
        ("front", 1, "left"),
        ("front", 1, "top"),
    ]
    # 未给出内容矩形的页不产生越线
    result = _check([], total_pages=1)
    assert result["violations"] == []


def test_multi_signature_reports_signature_and_sheet_index():
    # 8 页、每帖 1 张 -> 2 帖；第 5 页在帖 2 正面右槽（x=100）
    result = _check(
        [(5, [(0, 0, 10, 10)])],
        total_pages=8,
    )
    assert [
        (v["signature_index"], v["sheet_index"], v["side"], v["page"], v["edge"])
        for v in result["violations"]
    ] == [(2, 1, "front", 5, "left"), (2, 1, "front", 5, "top")]


def test_multi_sheet_signature_reports_sheet_index():
    # 8 页、每帖 2 张 -> 1 帖 2 张；第 3 页在帖 1 第 2 张正面右槽（x=100）
    result = _check(
        [(3, [(0, 0, 10, 10)])],
        total_pages=8,
        max_sheets=2,
    )
    assert {
        (v["signature_index"], v["sheet_index"], v["page"]) for v in result["violations"]
    } == {(1, 2, 3)}


def test_violations_ordered_by_sheet_side_slot_rect_edge():
    # 同一请求多处越线的返回顺序：面（front 先于 back）-> 槽位（左先于右）-> 边序
    result = _check(
        [
            (1, [(0, 0, 10, 10)]),  # 正面右槽：左、上
            (4, [(0, 0, 10, 10)]),  # 正面左槽：左、上
            (2, [(0, 0, 10, 10)]),  # long 背面右槽：左、上
            (3, [(0, 0, 10, 10)]),  # long 背面左槽：左、上
        ]
    )
    assert [(v["side"], v["page"], v["edge"]) for v in result["violations"]] == [
        ("front", 4, "left"),
        ("front", 4, "top"),
        ("front", 1, "left"),
        ("front", 1, "top"),
        ("back", 3, "left"),
        ("back", 3, "top"),
        ("back", 2, "left"),
        ("back", 2, "top"),
    ]


def test_negative_or_non_finite_margins_raise():
    for margin in (-0.1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            _check([], trim_margin_mm=margin)
        with pytest.raises(ValueError):
            _check([], fold_margin_mm=margin)


def test_invalid_page_number_raises():
    with pytest.raises(ValueError):
        _check([(5, [(0, 0, 1, 1)])])
    with pytest.raises(ValueError):
        _check([(0, [(0, 0, 1, 1)])])


def test_duplicate_page_raises():
    with pytest.raises(ValueError):
        _check([
            (1, [(0, 0, 1, 1)]),
            (1, [(0, 0, 1, 1)]),
        ])


def test_empty_rectangles_raise():
    with pytest.raises(ValueError):
        _check([(1, [])])


def test_rect_out_of_page_raises():
    for rect in (
        (-0.1, 0.0, 10.0, 10.0),
        (0.0, -0.1, 10.0, 10.0),
        (0.0, 0.0, 100.1, 10.0),
        (95.0, 0.0, 10.0, 10.0),
        (0.0, 95.0, 10.0, 10.0),
        (0.0, 0.0, 0.0, 10.0),
        (0.0, 0.0, 10.0, -1.0),
    ):
        with pytest.raises(ValueError):
            _check([(1, [rect])])


def test_non_finite_rect_values_raise():
    for rect in (
        (float("nan"), 0.0, 10.0, 10.0),
        (0.0, float("inf"), 10.0, 10.0),
    ):
        with pytest.raises(ValueError):
            _check([(1, [rect])])


def test_invalid_duplex_flip_raises():
    with pytest.raises(ValueError):
        _check([], duplex_flip="side")
