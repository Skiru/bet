def test_work_order_hash_is_deterministic():
    from bet.pipeline.runtime_selection import RuntimeStageWorkOrder

    order = RuntimeStageWorkOrder("p", "r", "r", "S2", "event", "c" * 64, "a" * 64, "b" * 64, "d" * 64, "e" * 64, ("1",), (), ())
    assert len(order.sha256) == 64
