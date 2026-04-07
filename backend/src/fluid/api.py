from flask import Blueprint, request, jsonify
from .fluid_analysis import run_fluid_analysis
from ..utils.setting.paths import bucket
import os
import json
import logging

fluid_bp = Blueprint('fluid', __name__)
LOGGER = logging.getLogger(__name__)


@fluid_bp.route('/run', methods=['POST'])
def run_analysis():
    """同步执行流体指标分析（向后兼容）。"""
    data = request.get_json() or {}
    topic = data.get('topic')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not topic or not start_date:
        return jsonify({"status": "error", "message": "Missing topic or start_date"}), 400

    try:
        success = run_fluid_analysis(topic, start_date, end_date)
        if success:
            return jsonify({"status": "ok", "message": "Analysis started successfully"})
        else:
            return jsonify({"status": "error", "message": "Analysis failed to start"}), 500
    except Exception as e:
        LOGGER.exception("Error running fluid analysis")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/run-async', methods=['POST'])
def run_analysis_async():
    """异步执行流体指标分析（后台worker模式）。"""
    from server_support.fluid_analysis import create_or_reuse_task, ensure_worker_running  # type: ignore

    data = request.get_json() or {}
    topic = data.get('topic')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    window_hours = data.get('window_hours', 3)
    target_file = data.get('target_file')
    force = data.get('force', False)

    if not topic or not start_date:
        return jsonify({"status": "error", "message": "Missing topic or start_date"}), 400

    try:
        task = create_or_reuse_task(
            topic,
            start_date,
            end_date=end_date,
            window_hours=window_hours,
            target_file=target_file,
            force=force,
        )
        ensure_worker_running()
        return jsonify({
            "status": "ok",
            "message": "任务已创建",
            "task_id": task.get("id"),
            "task_status": task.get("status"),
            "task": task,
        })
    except Exception as e:
        LOGGER.exception("Error creating fluid indicator task")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """获取任务状态。"""
    from server_support.fluid_analysis import get_task  # type: ignore

    try:
        task = get_task(task_id)
        return jsonify({"status": "ok", "task": task})
    except LookupError:
        return jsonify({"status": "error", "message": "Task not found"}), 404
    except Exception as e:
        LOGGER.exception("Error getting fluid indicator task")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/task/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消任务。"""
    from server_support.fluid_analysis import cancel_task as do_cancel_task  # type: ignore

    try:
        task = do_cancel_task(task_id)
        return jsonify({"status": "ok", "task": task})
    except LookupError:
        return jsonify({"status": "error", "message": "Task not found"}), 404
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        LOGGER.exception("Error cancelling fluid indicator task")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/task/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除任务。"""
    from server_support.fluid_analysis import delete_task as do_delete_task  # type: ignore

    try:
        do_delete_task(task_id)
        return jsonify({"status": "ok", "message": "Task deleted"})
    except LookupError:
        return jsonify({"status": "error", "message": "Task not found"}), 404
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        LOGGER.exception("Error deleting fluid indicator task")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/status', methods=['GET'])
def get_status():
    """获取专题的流体指标任务状态。"""
    from server_support.fluid_analysis import build_status_payload  # type: ignore

    topic = request.args.get('topic')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not topic or not start_date:
        return jsonify({"status": "error", "message": "Missing topic or start_date"}), 400

    try:
        payload = build_status_payload(topic, start_date, end_date=end_date)
        return jsonify({"status": "ok", "data": payload})
    except Exception as e:
        LOGGER.exception("Error getting fluid indicator status")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/result', methods=['GET'])
def get_result():
    """获取流体指标分析结果。"""
    topic = request.args.get('topic')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not topic or not start_date:
        return jsonify({"status": "error", "message": "Missing topic or start_date"}), 400

    date_range = f"{start_date}_{end_date}" if end_date else start_date

    try:
        result_dir = bucket("fluid", topic, date_range)
        result_file = result_dir / "fluid_indicators_unified.json"

        if not result_file.exists():
            return jsonify({"status": "error", "message": "Result file not found"}), 404

        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return jsonify({"status": "ok", "data": data})

    except Exception as e:
        LOGGER.exception("Error retrieving fluid analysis result")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/archives', methods=['GET'])
def list_archives():
    """列出专题的所有流体指标分析存档。"""
    topic = request.args.get('topic')
    if not topic:
        return jsonify({"status": "error", "message": "Missing topic"}), 400

    try:
        base_dir = bucket("fluid", topic, "")

        if not base_dir.exists():
            return jsonify({"status": "ok", "data": []})

        archives = []
        for item in base_dir.iterdir():
            if item.is_dir():
                if (item / "fluid_indicators_unified.json").exists():
                    archives.append(item.name)

        archives.sort(reverse=True)

        return jsonify({"status": "ok", "data": archives})

    except Exception as e:
        LOGGER.exception("Error listing fluid archives")
        return jsonify({"status": "error", "message": str(e)}), 500


@fluid_bp.route('/worker', methods=['GET'])
def get_worker_status():
    """获取 worker 状态。"""
    from server_support.fluid_analysis import load_worker_status  # type: ignore

    try:
        status = load_worker_status()
        return jsonify({"status": "ok", "worker": status})
    except Exception as e:
        LOGGER.exception("Error getting fluid indicator worker status")
        return jsonify({"status": "error", "message": str(e)}), 500