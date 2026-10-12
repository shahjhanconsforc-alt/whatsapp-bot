def scrape_start(deps):
    request = deps["request"]
    start_scrape_job = deps["start_scrape_job"]
    resolve_scrape_profile_number = deps["resolve_scrape_profile_number"]
    jsonify = deps["jsonify"]
    profile_number = str(request.form.get("profile_number") or "").strip()
    if not profile_number:
        profile_number = str(resolve_scrape_profile_number() or "").strip()
    if not profile_number:
        return jsonify({"ok": False, "error": "No saved scrape profile number found for Profile 1."}), 400
    started = start_scrape_job(profile_number)
    if not started:
        return jsonify({"ok": False, "error": "Scrapping is already running."}), 409
    return jsonify({"ok": True})
