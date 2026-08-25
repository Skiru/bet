def test_work_order_contains_distinct_execute_and_reuse_sets():
    from bet.pipeline.runtime_selection import RuntimeStageWorkOrder
    order = RuntimeStageWorkOrder("p", "r", "r", "S2", "event", "c" * 64, "a" * 64, "b" * 64, "d" * 64, "e" * 64, ("1",), ("2",), ())
    assert order.execute_event_ids != order.reuse_event_ids
