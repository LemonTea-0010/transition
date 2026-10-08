import pytest

from transition_experiment.agent import explicit_unfinished, validate_reply
from transition_experiment.ctrip_eval import evaluate_ctrip
from transition_experiment.run import TriggerObserver
from transition_experiment.tasks import TASKS


def reply(status="in_progress", summary="已记录两个候选，还缺第三个候选。"):
    return {
        "current_subtask": "S3", "subtask_status": status,
        "progress_summary": summary, "next_subtask": "S4",
        "action": {"type": "scroll", "x": None, "y": None, "direction": "down",
                   "text": None, "target_description": "继续查看第三个候选"},
    }


def test_explicit_state_contract():
    previous = {"current_subtask": "S2", "subtask_status": "completed"}
    decision, state = validate_reply(reply(), 1280, 800, previous)
    assert state["current_subtask"] == "S3"
    assert decision["action"] == "scroll"
    assert explicit_unfinished(state["progress_summary"])


def test_s3_requires_progress_and_completed_transition():
    previous = {"current_subtask": "S2", "subtask_status": "in_progress"}
    with pytest.raises(ValueError, match="Previous S2 was in_progress"):
        validate_reply(reply(), 1280, 800, previous)
    previous = {"current_subtask": "S2", "subtask_status": "completed"}
    finished = reply("completed", "三个候选均已记录完成。")
    with pytest.raises(ValueError, match="two prior in_progress"):
        validate_reply(finished, 1280, 800, previous, s3_progress_count=1)
    _, state = validate_reply(finished, 1280, 800, previous, s3_progress_count=2)
    assert state["next_subtask"] == "S4"


def test_completed_s5_accepts_no_next_subtask():
    final = reply("completed", "推荐候选二，任务完成。")
    final["current_subtask"] = "S5"
    final["next_subtask"] = None
    final["action"] = {"type": "stop", "x": None, "y": None, "direction": None,
                       "text": None, "target_description": "推荐候选二并停止"}
    previous = {"current_subtask": "S4", "subtask_status": "completed"}
    decision, _ = validate_reply(final, 1280, 800, previous)
    assert decision["action"] == "stop"


def test_transition_requires_completed_s3_and_s4():
    class Page:
        def __init__(self):
            self.injected = False

        def evaluate(self, *_args):
            self.injected = True
            return 2500

    page = Page()
    observer = TriggerObserver(page, TASKS["taobao_compare_001"], "transition_high")
    metadata = {"agent_state": {"current_subtask": "S3", "subtask_status": "in_progress",
                                "next_subtask": "S4", "progress_summary": "还缺一个候选"},
                "action_status": "executed"}
    observer.after(page, {"action": "scroll"}, metadata, 7)
    assert observer.event is None
    metadata["agent_state"]["subtask_status"] = "completed"
    observer.after(page, {"action": "scroll"}, metadata, 11)
    assert observer.event["triggered_after_step"] == 11


def test_ctrip_transition_triggers_after_s2_completes():
    class Page:
        def evaluate(self, *_args):
            return True

    observer = TriggerObserver(Page(), TASKS["ctrip_hotel_compare_001"], "transition_high")
    metadata = {"agent_state": {"current_subtask": "S2", "subtask_status": "in_progress",
                                "next_subtask": "S3"}, "action_status": "executed"}
    observer.after(observer.page, {"action": "scroll"}, metadata, 3)
    assert observer.event is None
    metadata["agent_state"]["subtask_status"] = "completed"
    metadata["action_status"] = "failed"
    observer.after(observer.page, {"action": "scroll"}, metadata, 4)
    assert observer.event is None
    metadata["action_status"] = "executed"
    observer.after(observer.page, {"action": "scroll"}, metadata, 5)
    assert observer.event["triggered_after_step"] == 5
    assert observer.event["next_subtask"] == "S3"


def test_within_requires_prior_valid_s3_action():
    class Page:
        def evaluate(self, *_args):
            return True

    page = Page()
    observer = TriggerObserver(page, TASKS["taobao_compare_001"], "within_low")
    metadata = {"agent_state": {"current_subtask": "S3", "subtask_status": "in_progress",
                                "next_subtask": "S4", "progress_summary": "还缺一个候选"},
                "action_status": "executed"}
    observer.after(page, {"action": "scroll"}, metadata, 3)
    assert observer.event is None
    observer.after(page, {"action": "scroll"}, metadata, 9)
    assert observer.event["triggered_after_step"] == 9


def test_ctrip_recommendation_can_reference_previously_reported_price():
    candidates = [
        {"index": 5, "name": "如家", "price": 167, "reviews": 4056},
        {"index": 9, "name": "非繁", "price": 166, "reviews": 13},
        {"index": 12, "name": "浦东温德姆", "price": 395, "reviews": 6578},
    ]
    summary = ("第5个如家¥167/4,056条；第9个非繁¥166/13条；"
               "第12个浦东温德姆¥395/6,578条。推荐第12个浦东温德姆，因其点评数6,578最多。")
    trajectory = [{"agent_state": {"current_subtask": "S5", "subtask_status": "completed",
                                    "progress_summary": summary},
                   "action": {"type": "stop"}}]
    result = evaluate_ctrip(trajectory, {"candidates": candidates,
                                         "recommendation": candidates[2]})
    assert result["candidate_facts_match"]
    assert result["recommendation_correct"]
