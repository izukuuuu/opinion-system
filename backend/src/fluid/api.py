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

@fluid_bp.route('/result', methods=['GET'])
def get_result():
    topic = request.args.get('topic')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not topic or not start_date:
        return jsonify({"status": "error", "message": "Missing topic or start_date"}), 400

    date_range = f"{start_date}_{end_date}" if end_date else start_date
    
    try:
        # Construct path to the result file
        # run_fluid_analysis saves to: out_dir / "fluid_indicators_unified.json"
        # out_dir is ensure_bucket("fluid", topic, date_range)
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
    topic = request.args.get('topic')
    if not topic:
        return jsonify({"status": "error", "message": "Missing topic"}), 400

    try:
        # bucket("fluid", topic, "") returns the parent directory for all date ranges
        # e.g. data/projects/topic/fluid/
        base_dir = bucket("fluid", topic, "")
        
        if not base_dir.exists():
            return jsonify({"status": "ok", "data": []})

        archives = []
        for item in base_dir.iterdir():
            if item.is_dir():
                # Check if it contains the result file
                if (item / "fluid_indicators_unified.json").exists():
                    archives.append(item.name)
        
        # Sort archives descending (latest first)
        # Assumes format YYYYMMDD or YYYYMMDD_YYYYMMDD
        archives.sort(reverse=True)

        return jsonify({"status": "ok", "data": archives})

    except Exception as e:
        LOGGER.exception("Error listing fluid archives")
        return jsonify({"status": "error", "message": str(e)}), 500
