def logs_status(deps):
    app_log_lock = deps["app_log_lock"]
    app_log_state = deps["app_log_state"]
    send_state = deps["send_state"]
    scrape_state = deps["scrape_state"]
    jsonify = deps["jsonify"]
    with app_log_lock:
        logs = list(app_log_state["logs"])
    return jsonify(
        {
            "logs": logs[-500:],
            "send_running": bool(send_state.get("running")),
            "scrape_running": bool(scrape_state.get("running")),
        }
    )

