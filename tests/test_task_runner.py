from abie_gpt.app.task_runner import TaskRunner


def test_task_completes_on_marker(database):
    runner = TaskRunner(database)
    runner.start("chat")
    step = runner.record_response("chat", "Готово\nTASK_COMPLETE")
    assert step.completed is True
    assert runner.is_running("chat") is False


def test_task_stops_on_iteration_limit(database):
    runner = TaskRunner(database)
    runner.start("chat", max_iterations=1)
    step = runner.record_response("chat", "Ещё работаю")
    assert step.stopped is True
    assert runner.is_running("chat") is False


def test_manual_stop_is_persistent(database):
    runner = TaskRunner(database)
    runner.start("chat")
    runner.stop("chat")
    assert runner.is_running("chat") is False
