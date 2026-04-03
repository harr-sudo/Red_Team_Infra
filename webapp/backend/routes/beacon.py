"""
Beacon management API routes.

Proxies requests to the Cobalt Strike REST API through the beacon service.
Registered with url_prefix='/api/beacon' in app.py.
"""

from flask import Blueprint, jsonify, request
from webapp.backend.services.beacon_service import beacon_service

bp = Blueprint("beacon", __name__)


@bp.route("/health", methods=["GET"])
def health():
    """Check REST API connection health."""
    result = beacon_service.health_check()
    status = "connected" if result["authenticated"] else (
        "reachable" if result["reachable"] else "disconnected"
    )
    return jsonify({"status": status, **result})


@bp.route("/configure", methods=["POST"])
def configure():
    """Configure REST API connection settings."""
    data = request.get_json() or {}
    password = data.get("password")
    port = data.get("port")

    beacon_service.configure(password=password, port=port)

    # Immediately check health with new config
    result = beacon_service.health_check()
    return jsonify({
        "success": result["authenticated"],
        "health": result,
    })


@bp.route("/list", methods=["GET"])
def list_beacons():
    """List all active beacons."""
    result = beacon_service.list_beacons()
    return jsonify(result)


@bp.route("/<bid>", methods=["GET"])
def get_beacon(bid):
    """Get beacon details."""
    result = beacon_service.get_beacon(bid)
    return jsonify(result)


@bp.route("/<bid>/command", methods=["POST"])
def console_command(bid):
    """Execute a console command on a beacon."""
    data = request.get_json() or {}
    command = data.get("command", "").strip()

    if not command:
        return jsonify({"success": False, "error": "No command provided"}), 400

    result = beacon_service.console_command(bid, command)
    return jsonify(result)


@bp.route("/<bid>/tasks", methods=["GET"])
def get_tasks(bid):
    """Get beacon task summary."""
    result = beacon_service.get_beacon_tasks(bid)
    return jsonify(result)


@bp.route("/activity/<bid>", methods=["GET"])
def get_activity_log(bid):
    """Get full task history with results (activity log)."""
    fmt = request.args.get('format', 'plain')
    if fmt == 'structured':
        result = beacon_service.get_beacon_tasks_structured(bid)
    else:
        result = beacon_service.get_beacon_tasks_detail(bid)
    return jsonify(result)


@bp.route("/tasks/all", methods=["GET"])
def get_all_tasks():
    """List all tasks server-wide (all beacons)."""
    return jsonify(beacon_service.list_all_tasks())


@bp.route("/task/<task_id>", methods=["GET"])
def get_task_detail(task_id):
    """Get detailed task output."""
    result = beacon_service.get_task_detail(task_id)
    return jsonify(result)


@bp.route("/<bid>/sleep", methods=["POST"])
def set_sleep(bid):
    """Set beacon sleep time (seconds)."""
    data = request.get_json() or {}
    sleep_time = data.get("sleep", data.get("sleepTime"))  # accept both field names
    jitter = data.get("jitter", 0)

    if sleep_time is None:
        return jsonify({"success": False, "error": "sleepTime required"}), 400

    try:
        sleep_time = int(sleep_time)
        jitter = int(jitter)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "sleepTime and jitter must be integers"}), 400

    if sleep_time < 0:
        return jsonify({"success": False, "error": "sleepTime cannot be negative"}), 400
    if jitter < 0 or jitter > 99:
        return jsonify({"success": False, "error": "jitter must be between 0 and 99"}), 400

    result = beacon_service.set_sleep(bid, sleep_time, jitter)
    return jsonify(result)


# ── File Browser ──
@bp.route("/<bid>/fs/ls", methods=["POST"])
def file_ls(bid):
    path = request.json.get("path") if request.json else None
    return jsonify(beacon_service.list_directory(bid, path))


@bp.route("/<bid>/fs/drives", methods=["POST"])
def file_drives(bid):
    return jsonify(beacon_service.get_drives(bid))


@bp.route("/<bid>/fs/mkdir", methods=["POST"])
def file_mkdir(bid):
    folder = (request.json or {}).get("folder", "") or (request.json or {}).get("path", "")
    if not folder:
        return jsonify({"success": False, "error": "folder required"}), 400
    return jsonify(beacon_service.make_directory(bid, folder))


@bp.route("/<bid>/fs/rm", methods=["POST"])
def file_rm(bid):
    path = (request.json or {}).get("path", "")
    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400
    return jsonify(beacon_service.remove_file(bid, path))


@bp.route("/<bid>/fs/download", methods=["POST"])
def file_download(bid):
    path = (request.json or {}).get("path", "")
    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400
    return jsonify(beacon_service.download_file(bid, path))


@bp.route("/<bid>/fs/upload", methods=["POST"])
def file_upload(bid):
    data = request.json or {}
    file_ref = data.get("file", "")
    if not file_ref:
        return jsonify({"success": False, "error": "file reference required (e.g. @files/name or @artifacts/path)"}), 400
    return jsonify(beacon_service.upload_file(bid, file_ref))


# ── Process Browser ──
@bp.route("/<bid>/ps", methods=["POST"])
def process_list(bid):
    return jsonify(beacon_service.list_processes(bid))


@bp.route("/<bid>/kill", methods=["POST"])
def process_kill(bid):
    pid = (request.json or {}).get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.kill_process(bid, pid))


# ── Screenshots ──
@bp.route("/<bid>/screenshot", methods=["POST"])
def screenshot_take(bid):
    return jsonify(beacon_service.take_screenshot(bid))


@bp.route("/<bid>/screenwatch", methods=["POST"])
def screenshot_watch(bid):
    return jsonify(beacon_service.start_screenwatch(bid))


@bp.route("/<bid>/screenshots", methods=["GET"])
def screenshot_list(bid):
    return jsonify(beacon_service.list_screenshots(bid))


# ── Token Management ──
@bp.route("/<bid>/token/make", methods=["POST"])
def token_make(bid):
    data = request.json or {}
    domain = data.get("domain", "")
    user = data.get("user", "")
    password = data.get("password", "")
    if not all([domain, user, password]):
        return jsonify({"success": False, "error": "Domain, user, and password required"}), 400
    return jsonify(beacon_service.make_token(bid, domain, user, password))


@bp.route("/<bid>/token/steal", methods=["POST"])
def token_steal(bid):
    pid = (request.json or {}).get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.steal_token(bid, pid))


@bp.route("/<bid>/token/rev2self", methods=["POST"])
def token_rev2self(bid):
    return jsonify(beacon_service.rev2self(bid))


@bp.route("/<bid>/getuid", methods=["POST"])
def beacon_getuid(bid):
    return jsonify(beacon_service.get_uid(bid))


# ── Jobs & Downloads ──
@bp.route("/<bid>/jobs", methods=["GET"])
def jobs_list(bid):
    return jsonify(beacon_service.list_jobs(bid))


@bp.route("/<bid>/jobs/<jid>/stop", methods=["POST"])
def jobs_kill(bid, jid):
    return jsonify(beacon_service.kill_job(bid, jid))


@bp.route("/<bid>/downloads", methods=["GET"])
def downloads_list(bid):
    return jsonify(beacon_service.list_downloads(bid))


@bp.route("/<bid>/downloads/active", methods=["GET"])
def downloads_active(bid):
    """List in-progress file transfers for this beacon."""
    return jsonify(beacon_service.list_active_downloads(bid))


@bp.route("/<bid>/downloads/cancel", methods=["POST"])
def downloads_cancel(bid):
    path = (request.json or {}).get("path", "")
    if not path:
        return jsonify({"success": False, "error": "File path required"}), 400
    return jsonify(beacon_service.cancel_download(bid, path))


# ── Credentials ──
@bp.route("/<bid>/creds/hashdump", methods=["POST"])
def creds_hashdump(bid):
    return jsonify(beacon_service.hashdump(bid))


@bp.route("/<bid>/creds/logonpasswords", methods=["POST"])
def creds_logonpasswords(bid):
    return jsonify(beacon_service.logonpasswords(bid))


@bp.route("/<bid>/creds/dcsync", methods=["POST"])
def creds_dcsync(bid):
    data = request.json or {}
    domain = data.get("domain", "")
    user = data.get("user", "")
    if not domain:
        return jsonify({"success": False, "error": "Domain required"}), 400
    return jsonify(beacon_service.dcsync(bid, domain, user))


@bp.route("/<bid>/creds/mimikatz", methods=["POST"])
def creds_mimikatz(bid):
    args = (request.json or {}).get("args", "")
    if not args:
        return jsonify({"success": False, "error": "Mimikatz arguments required"}), 400
    return jsonify(beacon_service.mimikatz(bid, args))


# ── Network Recon ──
@bp.route("/<bid>/net/<subcmd>", methods=["POST"])
def net_recon(bid, subcmd):
    valid = [
        "computers", "dclist", "domain", "groups", "users",
        "shares", "sessions", "logons", "trusts",
    ]
    if subcmd not in valid:
        return jsonify({
            "success": False,
            "error": f"Invalid subcommand. Valid: {', '.join(valid)}",
        }), 400
    target = request.json.get("target") if request.json else None
    return jsonify(beacon_service.net_command(bid, subcmd, target))


@bp.route("/<bid>/portscan", methods=["POST"])
def net_portscan(bid):
    data = request.json or {}
    targets = data.get("targets", "")
    ports = data.get("ports", "")
    method = data.get("method", "arp")
    if not targets or not ports:
        return jsonify({"success": False, "error": "Targets and ports required"}), 400
    return jsonify(beacon_service.portscan(bid, targets, ports, method))


# ── Pivoting ──
@bp.route("/<bid>/socks/start", methods=["POST"])
def pivot_socks_start(bid):
    data = request.json or {}
    port = data.get("port")
    version = data.get("version", "socks5")
    if not port:
        return jsonify({"success": False, "error": "Port required"}), 400
    return jsonify(beacon_service.socks_start(bid, port, version))


@bp.route("/<bid>/socks/stop", methods=["POST"])
def pivot_socks_stop(bid):
    return jsonify(beacon_service.socks_stop(bid))


@bp.route("/<bid>/rportfwd/start", methods=["POST"])
def pivot_rportfwd_start(bid):
    data = request.json or {}
    bind_port = data.get("bindPort")
    fwd_host = data.get("forwardHost")
    fwd_port = data.get("forwardPort")
    if not all([bind_port, fwd_host, fwd_port]):
        return jsonify({
            "success": False,
            "error": "bindPort, forwardHost, and forwardPort required",
        }), 400
    return jsonify(beacon_service.rportfwd_start(bid, bind_port, fwd_host, fwd_port))


@bp.route("/<bid>/rportfwd/stop", methods=["POST"])
def pivot_rportfwd_stop(bid):
    bind_port = (request.json or {}).get("bindPort")
    if not bind_port:
        return jsonify({"success": False, "error": "bindPort required"}), 400
    return jsonify(beacon_service.rportfwd_stop(bid, bind_port))


# ── Listeners (server-level) ──
@bp.route("/listeners", methods=["GET"])
def listeners_list():
    return jsonify(beacon_service.list_listeners())


@bp.route("/listeners/<lid>", methods=["GET"])
def listeners_get(lid):
    return jsonify(beacon_service.get_listener(lid))


@bp.route("/listeners/<lid>", methods=["DELETE"])
def listeners_delete(lid):
    return jsonify(beacon_service.delete_listener(lid))


@bp.route("/listeners/create/<listener_type>", methods=["POST"])
def listeners_create(listener_type):
    valid_types = ["http", "https", "dns", "smb", "tcp", "externalC2", "foreignHttp", "foreignHttps", "userDefinedC2"]
    if listener_type not in valid_types:
        return jsonify({
            "success": False,
            "error": f"Invalid type. Valid: {', '.join(valid_types)}",
        }), 400
    config = request.json or {}
    return jsonify(beacon_service.create_listener(listener_type, config))


# ── Beacon Config ──
@bp.route("/<bid>/config/spawnto", methods=["POST"])
def config_spawnto(bid):
    data = request.json or {}
    arch = data.get("arch", "x64")
    path = data.get("path", "")
    if not path:
        return jsonify({"success": False, "error": "Path required"}), 400
    return jsonify(beacon_service.set_spawnto(bid, arch, path))


@bp.route("/<bid>/config/ppid", methods=["POST"])
def config_ppid(bid):
    pid = (request.json or {}).get("pid")
    if pid is None:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.set_ppid(bid, pid))


@bp.route("/<bid>/config/ppid", methods=["DELETE"])
def config_ppid_clear(bid):
    return jsonify(beacon_service.clear_ppid(bid))


@bp.route("/<bid>/config/blockdlls", methods=["POST"])
def config_blockdlls(bid):
    enabled = (request.json or {}).get("enabled", True)
    return jsonify(beacon_service.set_blockdlls(bid, enabled))


@bp.route("/<bid>/config/argue", methods=["POST"])
def config_argue(bid):
    data = request.json or {}
    command = data.get("command", "")
    args = data.get("args", "")
    if not command:
        return jsonify({"success": False, "error": "Command required"}), 400
    if not args:
        return jsonify({"success": False, "error": "args (fakeArguments) required"}), 400
    return jsonify(beacon_service.set_argue(bid, command, args))


@bp.route("/<bid>/config/dnsmode", methods=["POST"])
def config_dnsmode(bid):
    mode = (request.json or {}).get("mode", "dns")
    valid_modes = ["dns", "dns6", "dnsTxt"]
    if mode not in valid_modes:
        return jsonify({"success": False, "error": f"Invalid mode. Valid: {', '.join(valid_modes)}"}), 400
    return jsonify(beacon_service.set_dns_mode(bid, mode))


# ── BOF Execution (BETA) ──
@bp.route("/<bid>/bof/execute", methods=["POST"])
def bof_execute(bid):
    """Execute a BOF with typed arguments."""
    data = request.json or {}
    bof = data.get("bof", "")
    if not bof:
        return jsonify({"success": False, "error": "BOF reference required"}), 400
    method = data.get("method", "pack")  # string, pack, or packed
    entrypoint = data.get("entrypoint", "go")
    arguments = data.get("arguments")
    files = data.get("files")
    if method == "string":
        return jsonify(beacon_service.execute_bof_string(bid, bof, entrypoint, arguments or "", files))
    elif method == "packed":
        return jsonify(beacon_service.execute_bof_packed(bid, bof, entrypoint, arguments or "", files))
    else:
        return jsonify(beacon_service.execute_bof_pack(bid, bof, entrypoint, arguments, files))


@bp.route("/artifacts", methods=["GET"])
def list_artifacts():
    """List available artifacts on the team server."""
    return jsonify(beacon_service.list_artifacts())


# ── Token Store (BETA) ──
@bp.route("/<bid>/tokenstore/list", methods=["POST"])
def token_store_list(bid):
    return jsonify(beacon_service.token_store_list(bid))


@bp.route("/<bid>/tokenstore/steal", methods=["POST"])
def token_store_steal(bid):
    pid = (request.json or {}).get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.token_store_steal(bid, int(pid)))


@bp.route("/<bid>/tokenstore/use", methods=["POST"])
def token_store_use(bid):
    token_id = (request.json or {}).get("id")
    if token_id is None:
        return jsonify({"success": False, "error": "Token ID required"}), 400
    return jsonify(beacon_service.token_store_use(bid, int(token_id)))


@bp.route("/<bid>/tokenstore/steal-and-use", methods=["POST"])
def token_store_steal_and_use(bid):
    pid = (request.json or {}).get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.token_store_steal_and_use(bid, int(pid)))


@bp.route("/<bid>/tokenstore/remove", methods=["POST"])
def token_store_remove(bid):
    ids = (request.json or {}).get("ids", [])
    if not ids:
        return jsonify({"success": False, "error": "Token IDs required"}), 400
    return jsonify(beacon_service.token_store_remove(bid, ids))


@bp.route("/<bid>/tokenstore/remove-all", methods=["POST"])
def token_store_remove_all(bid):
    return jsonify(beacon_service.token_store_remove_all(bid))


# ── Credential Vault ──
@bp.route("/data/credentials", methods=["GET"])
def credentials_list():
    return jsonify(beacon_service.list_credentials())


@bp.route("/data/credentials", methods=["POST"])
def credentials_add():
    data = request.json or {}
    for field in ["user", "password", "realm"]:
        if not data.get(field):
            return jsonify({"success": False, "error": f"{field} required"}), 400
    return jsonify(beacon_service.add_credential(data))


@bp.route("/data/credentials/<cred_id>", methods=["GET"])
def credentials_get(cred_id):
    return jsonify(beacon_service.get_credential(cred_id))


@bp.route("/data/credentials/<cred_id>", methods=["DELETE"])
def credentials_delete(cred_id):
    return jsonify(beacon_service.delete_credential(cred_id))


# ── C2 Host Management (BETA) ──
@bp.route("/<bid>/c2/hosts", methods=["GET"])
def c2_hosts_get(bid):
    return jsonify(beacon_service.get_c2_hosts(bid))


@bp.route("/<bid>/c2/hosts", methods=["POST"])
def c2_hosts_add(bid):
    infos = (request.json or {}).get("infos", [])
    if not infos:
        return jsonify({"success": False, "error": "Host info required"}), 400
    return jsonify(beacon_service.add_c2_host(bid, infos))


@bp.route("/<bid>/c2/hosts", methods=["PUT"])
def c2_hosts_update(bid):
    infos = (request.json or {}).get("infos", [])
    if not infos:
        return jsonify({"success": False, "error": "Host update info required"}), 400
    return jsonify(beacon_service.update_c2_host(bid, infos))


@bp.route("/<bid>/c2/hosts", methods=["DELETE"])
def c2_hosts_delete(bid):
    hostnames = (request.json or {}).get("hostnames", [])
    if not hostnames:
        return jsonify({"success": False, "error": "Hostnames required"}), 400
    return jsonify(beacon_service.delete_c2_host(bid, hostnames))


@bp.route("/<bid>/c2/hosts/hold", methods=["POST"])
def c2_hosts_hold(bid):
    hostnames = (request.json or {}).get("hostnames", [])
    if not hostnames:
        return jsonify({"success": False, "error": "Hostnames required"}), 400
    return jsonify(beacon_service.hold_c2_host(bid, hostnames))


@bp.route("/<bid>/c2/hosts/release", methods=["POST"])
def c2_hosts_release(bid):
    hostnames = (request.json or {}).get("hostnames", [])
    if not hostnames:
        return jsonify({"success": False, "error": "Hostnames required"}), 400
    return jsonify(beacon_service.release_c2_host(bid, hostnames))


@bp.route("/<bid>/c2/hosts/reset", methods=["POST"])
def c2_hosts_reset(bid):
    data = request.json or {}
    action = data.get("action", "all")
    hostnames = data.get("hostnames")
    return jsonify(beacon_service.reset_c2_host(bid, action, hostnames))


@bp.route("/<bid>/c2/hosts/profiles", methods=["GET"])
def c2_host_profiles(bid):
    return jsonify(beacon_service.get_c2_host_profiles(bid))


@bp.route("/<bid>/c2/failover", methods=["GET"])
def c2_failover_get(bid):
    return jsonify(beacon_service.get_failover_notification(bid))


@bp.route("/<bid>/c2/failover/enable", methods=["POST"])
def c2_failover_enable(bid):
    return jsonify(beacon_service.enable_failover_notification(bid))


@bp.route("/<bid>/c2/failover/disable", methods=["POST"])
def c2_failover_disable(bid):
    return jsonify(beacon_service.disable_failover_notification(bid))


# ── Beacon Gate & Syscall (BETA) ──
@bp.route("/<bid>/config/beacongate/enable", methods=["POST"])
def config_beacongate_enable(bid):
    return jsonify(beacon_service.enable_beacon_gate(bid))


@bp.route("/<bid>/config/beacongate/disable", methods=["POST"])
def config_beacongate_disable(bid):
    return jsonify(beacon_service.disable_beacon_gate(bid))


@bp.route("/<bid>/config/syscall", methods=["GET"])
def config_syscall_get(bid):
    return jsonify(beacon_service.get_syscall_method(bid))


@bp.route("/<bid>/config/syscall", methods=["POST"])
def config_syscall_set(bid):
    method = (request.json or {}).get("method", "None")
    valid = ["None", "Direct", "Indirect"]
    if method not in valid:
        return jsonify({"success": False, "error": f"Invalid method. Valid: {', '.join(valid)}"}), 400
    return jsonify(beacon_service.set_syscall_method(bid, method))


# ── Payload Generation (BETA) ──
@bp.route("/payloads/generate/stageless", methods=["POST"])
def payload_generate_stageless():
    config = request.json or {}
    required = ["listenerName", "architecture", "exitFunction", "systemCallMethod", "output", "useListenerGuardRails"]
    for field in required:
        if field not in config:
            return jsonify({"success": False, "error": f"{field} required"}), 400
    return jsonify(beacon_service.generate_stageless_payload(config))


@bp.route("/payloads/generate/stager", methods=["POST"])
def payload_generate_stager():
    config = request.json or {}
    for field in ["listenerName", "architecture", "output"]:
        if not config.get(field):
            return jsonify({"success": False, "error": f"{field} required"}), 400
    return jsonify(beacon_service.generate_stager_payload(config))


@bp.route("/payloads/<filename>", methods=["GET"])
def payload_download(filename):
    """Download a generated payload binary."""
    from flask import Response
    result = beacon_service.get_payload(filename)
    if not result.get("success"):
        return jsonify(result)
    return Response(
        result["content"],
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Server Config ──
@bp.route("/server/killdate", methods=["GET"])
def server_killdate():
    return jsonify(beacon_service.get_killdate())


@bp.route("/server/profile", methods=["GET"])
def server_profile():
    return jsonify(beacon_service.get_malleable_profile())


@bp.route("/server/info", methods=["GET"])
def server_info():
    return jsonify(beacon_service.get_system_information())


@bp.route("/server/ip", methods=["GET"])
def server_ip():
    return jsonify(beacon_service.get_teamserver_ip())


# ── Beacon Management ──
@bp.route("/<bid>/delete", methods=["DELETE"])
def beacon_delete(bid):
    return jsonify(beacon_service.delete_beacon(bid))


@bp.route("/<bid>/clear-queue", methods=["POST"])
def beacon_clear_queue(bid):
    return jsonify(beacon_service.clear_command_queue(bid))


@bp.route("/<bid>/checkin", methods=["POST"])
def beacon_checkin(bid):
    return jsonify(beacon_service.force_checkin(bid))


@bp.route("/<bid>/note", methods=["POST"])
def beacon_note(bid):
    note = (request.json or {}).get("note", "")
    return jsonify(beacon_service.set_beacon_note(bid, note))


@bp.route("/<bid>/info", methods=["POST"])
def beacon_info(bid):
    """Get beacon memory diagnostics."""
    return jsonify(beacon_service.get_beacon_info(bid))


# ── Listener Editing ──
@bp.route("/listeners/update/<listener_type>/<name>", methods=["PUT"])
def listeners_update(listener_type, name):
    valid_types = ["http", "https", "dns", "smb", "tcp", "externalC2", "foreignHttp", "foreignHttps", "userDefinedC2"]
    if listener_type not in valid_types:
        return jsonify({"success": False, "error": f"Invalid type. Valid: {', '.join(valid_types)}"}), 400
    config = request.json or {}
    return jsonify(beacon_service.update_listener(listener_type, name, config))


# ── Screenshots Gallery (server-wide) ──
@bp.route("/data/screenshots", methods=["GET"])
def screenshots_list_all():
    return jsonify(beacon_service.list_all_screenshots())


@bp.route("/data/screenshots/<screenshot_id>", methods=["GET"])
def screenshots_get(screenshot_id):
    return jsonify(beacon_service.get_screenshot(screenshot_id))


@bp.route("/data/screenshots/<screenshot_id>", methods=["DELETE"])
def screenshots_delete(screenshot_id):
    return jsonify(beacon_service.delete_screenshot(screenshot_id))


# ── Keystrokes (server-wide) ──
@bp.route("/data/keystrokes", methods=["GET"])
def keystrokes_list_all():
    return jsonify(beacon_service.list_all_keystrokes())


@bp.route("/<bid>/keystrokes", methods=["GET"])
def keystrokes_list_beacon(bid):
    return jsonify(beacon_service.list_beacon_keystrokes(bid))


@bp.route("/data/keystrokes/<keystroke_id>", methods=["DELETE"])
def keystrokes_delete(keystroke_id):
    return jsonify(beacon_service.delete_keystrokes(keystroke_id))


# ── Downloads Manager (server-wide) ──
@bp.route("/data/downloads", methods=["GET"])
def downloads_list_all():
    return jsonify(beacon_service.list_all_downloads())


@bp.route("/data/downloads/<download_id>", methods=["GET"])
def downloads_get(download_id):
    return jsonify(beacon_service.get_download(download_id))


@bp.route("/data/downloads/<download_id>", methods=["DELETE"])
def downloads_delete(download_id):
    return jsonify(beacon_service.delete_download(download_id))


# ── Spawn/Inject Variants (BETA) ──
# All inject endpoints require {arch, pid} per OpenAPI spec.
# All spawn endpoints have no required body (or minimal).
# Refer to docs/cobalt-strike-api/spec.js for exact DTO schemas.

@bp.route("/<bid>/spawn/hashdump", methods=["POST"])
def spawn_hashdump(bid):
    return jsonify(beacon_service.spawn_hashdump(bid))


@bp.route("/<bid>/inject/hashdump", methods=["POST"])
def inject_hashdump(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_hashdump(bid, int(pid), data.get("arch", "x64")))


@bp.route("/<bid>/spawn/logonpasswords", methods=["POST"])
def spawn_logonpasswords(bid):
    return jsonify(beacon_service.spawn_logonpasswords(bid))


@bp.route("/<bid>/inject/logonpasswords", methods=["POST"])
def inject_logonpasswords(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_logonpasswords(bid, int(pid), data.get("arch", "x64")))


@bp.route("/<bid>/spawn/screenshot", methods=["POST"])
def spawn_screenshot(bid):
    return jsonify(beacon_service.spawn_screenshot(bid))


@bp.route("/<bid>/inject/screenshot", methods=["POST"])
def inject_screenshot(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_screenshot(bid, int(pid), data.get("arch", "x64")))


@bp.route("/<bid>/spawn/keylogger", methods=["POST"])
def spawn_keylogger(bid):
    return jsonify(beacon_service.spawn_keylogger(bid))


@bp.route("/<bid>/inject/keylogger", methods=["POST"])
def inject_keylogger(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_keylogger(bid, int(pid), data.get("arch", "x64")))


@bp.route("/<bid>/spawn/execute-assembly", methods=["POST"])
def spawn_execute_assembly(bid):
    data = request.json or {}
    assembly = data.get("assembly", "")
    if not assembly:
        return jsonify({"success": False, "error": "Assembly reference required"}), 400
    return jsonify(beacon_service.spawn_execute_assembly(bid, assembly, data.get("arguments", ""), data.get("files")))


@bp.route("/<bid>/spawn/chromedump", methods=["POST"])
def spawn_chromedump(bid):
    return jsonify(beacon_service.spawn_chromedump(bid))


@bp.route("/<bid>/inject/chromedump", methods=["POST"])
def inject_chromedump(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_chromedump(bid, int(pid), data.get("arch", "x64")))


@bp.route("/<bid>/spawn/dcsync", methods=["POST"])
def spawn_dcsync(bid):
    data = request.json or {}
    domain = data.get("domain", "")
    if not domain:
        return jsonify({"success": False, "error": "domain required"}), 400
    return jsonify(beacon_service.spawn_dcsync(bid, domain, data.get("user")))


@bp.route("/<bid>/inject/dcsync", methods=["POST"])
def inject_dcsync(bid):
    data = request.json or {}
    pid = data.get("pid")
    domain = data.get("domain", "")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    if not domain:
        return jsonify({"success": False, "error": "domain required"}), 400
    return jsonify(beacon_service.inject_dcsync(bid, int(pid), data.get("arch", "x64"), domain, data.get("user")))


@bp.route("/<bid>/spawn/mimikatz", methods=["POST"])
def spawn_mimikatz(bid):
    data = request.json or {}
    command = data.get("command", "")
    mode = data.get("mode", "normal")
    valid_modes = ["normal", "elevate", "impersonate"]
    if mode not in valid_modes:
        return jsonify({"success": False, "error": f"Invalid mode. Valid: {', '.join(valid_modes)}"}), 400
    return jsonify(beacon_service.spawn_mimikatz(bid, command, mode))


@bp.route("/<bid>/inject/mimikatz", methods=["POST"])
def inject_mimikatz(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    command = data.get("command", "")
    mode = data.get("mode", "normal")
    valid_modes = ["normal", "elevate", "impersonate"]
    if mode not in valid_modes:
        return jsonify({"success": False, "error": f"Invalid mode. Valid: {', '.join(valid_modes)}"}), 400
    return jsonify(beacon_service.inject_mimikatz(bid, int(pid), command, mode, data.get("arch", "x64")))


@bp.route("/<bid>/spawn/portscan", methods=["POST"])
def spawn_portscan(bid):
    data = request.json or {}
    targets = data.get("targets", [])
    ports = data.get("ports", [])
    if isinstance(targets, str):
        targets = [targets] if targets else []
    if isinstance(ports, str):
        ports = [ports] if ports else []
    if not targets or not ports:
        return jsonify({"success": False, "error": "targets and ports arrays required"}), 400
    return jsonify(beacon_service.spawn_portscan(
        bid, targets, ports,
        data.get("method", "arp"), data.get("maxConnections", 1024),
    ))


@bp.route("/<bid>/inject/portscan", methods=["POST"])
def inject_portscan(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    targets = data.get("targets", [])
    ports = data.get("ports", [])
    if isinstance(targets, str):
        targets = [targets] if targets else []
    if isinstance(ports, str):
        ports = [ports] if ports else []
    if not targets or not ports:
        return jsonify({"success": False, "error": "targets and ports arrays required"}), 400
    return jsonify(beacon_service.inject_portscan(
        bid, int(pid), targets, ports,
        data.get("method", "arp"), data.get("arch", "x64"), data.get("maxConnections", 1024),
    ))


@bp.route("/<bid>/spawn/screenwatch", methods=["POST"])
def spawn_screenwatch(bid):
    return jsonify(beacon_service.spawn_screenwatch(bid))


@bp.route("/<bid>/inject/screenwatch", methods=["POST"])
def inject_screenwatch(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_screenwatch(bid, int(pid), data.get("arch", "x64")))


@bp.route("/<bid>/spawn/printscreen", methods=["POST"])
def spawn_printscreen(bid):
    return jsonify(beacon_service.spawn_printscreen(bid))


@bp.route("/<bid>/inject/printscreen", methods=["POST"])
def inject_printscreen(bid):
    data = request.json or {}
    pid = data.get("pid")
    if not pid:
        return jsonify({"success": False, "error": "PID required"}), 400
    return jsonify(beacon_service.inject_printscreen(bid, int(pid), data.get("arch", "x64")))


# ── Privilege Escalation Info ──
@bp.route("/<bid>/elevate/methods", methods=["GET"])
def elevate_methods(bid):
    return jsonify(beacon_service.list_elevate_methods(bid))


@bp.route("/<bid>/runasadmin/methods", methods=["GET"])
def runasadmin_methods(bid):
    return jsonify(beacon_service.list_runasadmin_methods(bid))


# ── Remote Execution Info ──
@bp.route("/<bid>/jump/methods", methods=["GET"])
def jump_methods(bid):
    return jsonify(beacon_service.list_jump_methods(bid))


@bp.route("/<bid>/remote-exec/methods", methods=["GET"])
def remote_exec_methods(bid):
    return jsonify(beacon_service.list_remote_exec_methods(bid))


# ══════════════════════════════════════════════════════════════════
# FULL SPEC COVERAGE — remaining endpoints
# ══════════════════════════════════════════════════════════════════

# ── File & Registry operations ──
@bp.route("/<bid>/fs/cd", methods=["POST"])
def file_cd(bid):
    path = (request.json or {}).get("path", "")
    if not path:
        return jsonify({"success": False, "error": "path required"}), 400
    return jsonify(beacon_service.change_directory(bid, path))


@bp.route("/<bid>/fs/cp", methods=["POST"])
def file_cp(bid):
    data = request.json or {}
    if not data.get("src") or not data.get("dst"):
        return jsonify({"success": False, "error": "src and dst required"}), 400
    return jsonify(beacon_service.copy_file(bid, data["src"], data["dst"]))


@bp.route("/<bid>/fs/mv", methods=["POST"])
def file_mv(bid):
    data = request.json or {}
    if not data.get("source") or not data.get("destination"):
        return jsonify({"success": False, "error": "source and destination required"}), 400
    return jsonify(beacon_service.move_file(bid, data["source"], data["destination"]))


@bp.route("/<bid>/fs/pwd", methods=["POST"])
def file_pwd(bid):
    return jsonify(beacon_service.print_working_directory(bid))


@bp.route("/<bid>/reg/query", methods=["POST"])
def reg_query(bid):
    data = request.json or {}
    if not data.get("arch") or not data.get("path"):
        return jsonify({"success": False, "error": "arch and path required"}), 400
    return jsonify(beacon_service.reg_query(bid, data["arch"], data["path"]))


@bp.route("/<bid>/reg/queryv", methods=["POST"])
def reg_queryv(bid):
    data = request.json or {}
    for f in ["arch", "path", "subkey"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.reg_queryv(bid, data["arch"], data["path"], data["subkey"]))


@bp.route("/<bid>/fs/timestomp", methods=["POST"])
def file_timestomp(bid):
    data = request.json or {}
    if not data.get("source") or not data.get("destination"):
        return jsonify({"success": False, "error": "source and destination required"}), 400
    return jsonify(beacon_service.timestomp(bid, data["source"], data["destination"]))


# ── Process & Execution ──
@bp.route("/<bid>/exit", methods=["POST"])
def beacon_exit(bid):
    return jsonify(beacon_service.exit_beacon(bid))


@bp.route("/<bid>/getprivs", methods=["POST"])
def beacon_getprivs(bid):
    return jsonify(beacon_service.get_privs(bid))


@bp.route("/<bid>/getsystem", methods=["POST"])
def beacon_getsystem(bid):
    return jsonify(beacon_service.get_system(bid))


@bp.route("/<bid>/setenv", methods=["POST"])
def beacon_setenv(bid):
    data = request.json or {}
    key = data.get("key", "") or data.get("name", "")
    if not key:
        return jsonify({"success": False, "error": "key required"}), 400
    return jsonify(beacon_service.set_env(bid, key, data.get("value", "")))


@bp.route("/<bid>/powershell/import", methods=["POST"])
def powershell_import(bid):
    data = request.json or {}
    if not data.get("script"):
        return jsonify({"success": False, "error": "script required"}), 400
    return jsonify(beacon_service.powershell_import(bid, data["script"]))


@bp.route("/<bid>/spawn/shell", methods=["POST"])
def spawn_shell(bid):
    command = (request.json or {}).get("command", "")
    if not command:
        return jsonify({"success": False, "error": "command required"}), 400
    return jsonify(beacon_service.spawn_shell(bid, command))


@bp.route("/<bid>/spawn/run", methods=["POST"])
def spawn_run(bid):
    data = request.json or {}
    if not data.get("program"):
        return jsonify({"success": False, "error": "program required"}), 400
    return jsonify(beacon_service.spawn_run(bid, data["program"], data.get("arguments", "")))


@bp.route("/<bid>/spawn/runas", methods=["POST"])
def spawn_run_as(bid):
    data = request.json or {}
    command = data.get("command", "") or data.get("program", "")
    for f in ["user", "password"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    if not command:
        return jsonify({"success": False, "error": "command required"}), 400
    return jsonify(beacon_service.spawn_run_as(bid, command, data.get("arguments", ""),
                                                data.get("domain", ""), data["user"], data["password"]))


@bp.route("/<bid>/spawn/rununder", methods=["POST"])
def spawn_run_under(bid):
    data = request.json or {}
    command = data.get("command", "") or data.get("program", "")
    if not command or data.get("pid") is None:
        return jsonify({"success": False, "error": "command and pid required"}), 400
    return jsonify(beacon_service.spawn_run_under(bid, command, data.get("arguments", ""), data["pid"]))


@bp.route("/<bid>/spawn/run-no-output", methods=["POST"])
def spawn_run_no_output(bid):
    data = request.json or {}
    cmd = data.get("cmd", "") or data.get("program", "")
    if not cmd:
        return jsonify({"success": False, "error": "cmd required"}), 400
    return jsonify(beacon_service.spawn_run_no_output(bid, cmd))


@bp.route("/<bid>/spawn/powershell", methods=["POST"])
def spawn_powershell(bid):
    data = request.json or {}
    commandlet = data.get("commandlet", "") or data.get("command", "")
    if not commandlet:
        return jsonify({"success": False, "error": "commandlet required"}), 400
    return jsonify(beacon_service.spawn_powershell(bid, commandlet, data.get("arguments", "")))


@bp.route("/<bid>/spawn/powerpick", methods=["POST"])
def spawn_powerpick(bid):
    data = request.json or {}
    commandlet = data.get("commandlet", "") or data.get("command", "")
    if not commandlet:
        return jsonify({"success": False, "error": "commandlet required"}), 400
    return jsonify(beacon_service.spawn_powerpick(bid, commandlet, data.get("arguments", "")))


@bp.route("/<bid>/inject/psinject", methods=["POST"])
def inject_psinject(bid):
    data = request.json or {}
    commandlet = data.get("commandlet", "") or data.get("command", "")
    if not data.get("pid") or not data.get("arch") or not commandlet:
        return jsonify({"success": False, "error": "pid, arch, and commandlet required"}), 400
    return jsonify(beacon_service.inject_psinject(bid, data["pid"], data["arch"], commandlet))


@bp.route("/<bid>/spawn/pth", methods=["POST"])
def spawn_pth(bid):
    data = request.json or {}
    for f in ["domain", "user", "ntlmHash"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.spawn_pth(bid, data["domain"], data["user"], data["ntlmHash"]))


@bp.route("/<bid>/inject/pth", methods=["POST"])
def inject_pth(bid):
    data = request.json or {}
    for f in ["pid", "arch", "domain", "user", "ntlmHash"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.inject_pth(bid, data["pid"], data["arch"], data["domain"], data["user"], data["ntlmHash"]))


@bp.route("/<bid>/spawn/shellcode", methods=["POST"])
def spawn_shellcode(bid):
    data = request.json or {}
    if not data.get("arch") or not data.get("shellcode"):
        return jsonify({"success": False, "error": "arch and shellcode required"}), 400
    return jsonify(beacon_service.spawn_shellcode(bid, data["arch"], data["shellcode"], data.get("files")))


@bp.route("/<bid>/inject/shellcode", methods=["POST"])
def inject_shellcode(bid):
    data = request.json or {}
    for f in ["pid", "arch", "shellcode"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.inject_shellcode(bid, data["pid"], data["arch"], data["shellcode"]))


@bp.route("/<bid>/spawn/beacon", methods=["POST"])
def spawn_beacon_session(bid):
    listener = (request.json or {}).get("listener", "")
    if not listener:
        return jsonify({"success": False, "error": "listener required"}), 400
    return jsonify(beacon_service.spawn_beacon(bid, listener))


@bp.route("/<bid>/spawn/beacon/asuser", methods=["POST"])
def spawn_beacon_as_user(bid):
    data = request.json or {}
    for f in ["listener", "domain", "user", "password"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.spawn_beacon_as_user(bid, data["listener"], data["domain"], data["user"], data["password"]))


@bp.route("/<bid>/spawn/beacon/under", methods=["POST"])
def spawn_beacon_under(bid):
    data = request.json or {}
    if not data.get("listener") or data.get("pid") is None:
        return jsonify({"success": False, "error": "listener and pid required"}), 400
    return jsonify(beacon_service.spawn_beacon_under(bid, data["listener"], data["pid"]))


@bp.route("/<bid>/inject/beacon", methods=["POST"])
def inject_beacon_session(bid):
    data = request.json or {}
    for f in ["pid", "arch", "listener"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.inject_beacon(bid, data["pid"], data["arch"], data["listener"]))


@bp.route("/<bid>/inject/dll", methods=["POST"])
def inject_dll(bid):
    data = request.json or {}
    if not data.get("pid") or not data.get("dll"):
        return jsonify({"success": False, "error": "pid and dll required"}), 400
    return jsonify(beacon_service.inject_dll(bid, data["pid"], data["dll"], data.get("files")))


@bp.route("/<bid>/inject/loaddll", methods=["POST"])
def inject_load_dll(bid):
    data = request.json or {}
    if not data.get("pid") or not data.get("path"):
        return jsonify({"success": False, "error": "pid and path required"}), 400
    return jsonify(beacon_service.inject_load_dll(bid, data["pid"], data["path"]))


# ── Privilege Escalation: execute ──
@bp.route("/<bid>/elevate/beacon", methods=["POST"])
def elevate_beacon(bid):
    data = request.json or {}
    if not data.get("exploit") or not data.get("listener"):
        return jsonify({"success": False, "error": "exploit and listener required"}), 400
    return jsonify(beacon_service.elevate_beacon(bid, data["exploit"], data["listener"]))


@bp.route("/<bid>/runasadmin", methods=["POST"])
def runasadmin_exec(bid):
    data = request.json or {}
    if not data.get("exploit") or not data.get("command"):
        return jsonify({"success": False, "error": "exploit and command required"}), 400
    return jsonify(beacon_service.run_as_admin(bid, data["exploit"], data["command"], data.get("arguments", "")))


# ── Remote Execution: execute ──
@bp.route("/<bid>/jump", methods=["POST"])
def jump_exec(bid):
    data = request.json or {}
    for f in ["exploit", "target", "listener"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.jump(bid, data["exploit"], data["target"], data["listener"]))


@bp.route("/<bid>/remote-exec", methods=["POST"])
def remote_exec(bid):
    data = request.json or {}
    for f in ["method", "target", "command"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.remote_exec(bid, data["method"], data["target"], data["command"]))


# ── Creds & Tokens: kerberos, UPN, postExDll ──
@bp.route("/<bid>/kerberos/use", methods=["POST"])
def kerberos_use(bid):
    ticket = (request.json or {}).get("ticket", "")
    if not ticket:
        return jsonify({"success": False, "error": "ticket required"}), 400
    return jsonify(beacon_service.kerberos_ticket_use(bid, ticket))


@bp.route("/<bid>/kerberos/purge", methods=["POST"])
def kerberos_purge(bid):
    return jsonify(beacon_service.kerberos_ticket_purge(bid))


@bp.route("/<bid>/token/make-upn", methods=["POST"])
def token_make_upn(bid):
    data = request.json or {}
    if not data.get("upn") or not data.get("password"):
        return jsonify({"success": False, "error": "upn and password required"}), 400
    return jsonify(beacon_service.make_token_upn(bid, data["upn"], data["password"]))


@bp.route("/<bid>/spawn/postexdll", methods=["POST"])
def spawn_post_ex_dll(bid):
    data = request.json or {}
    if not data.get("dll"):
        return jsonify({"success": False, "error": "dll required"}), 400
    return jsonify(beacon_service.spawn_post_ex_dll(bid, data["dll"], data.get("files")))


@bp.route("/<bid>/inject/postexdll", methods=["POST"])
def inject_post_ex_dll(bid):
    data = request.json or {}
    if not data.get("pid") or not data.get("dll"):
        return jsonify({"success": False, "error": "pid and dll required"}), 400
    return jsonify(beacon_service.inject_post_ex_dll(bid, data["pid"], data["dll"], data.get("files")))


# ── Network Recon: spawn/inject net variants ──
@bp.route("/<bid>/spawn/net/<subcmd>", methods=["POST"])
def spawn_net(bid, subcmd):
    valid = ["computers", "dclist", "domainControllers", "domainTrusts", "group",
             "localGroup", "logons", "sessions", "share", "time", "user", "view"]
    if subcmd not in valid:
        return jsonify({"success": False, "error": f"Invalid subcmd. Valid: {', '.join(valid)}"}), 400
    domain = (request.json or {}).get("domain", "")
    return jsonify(beacon_service.spawn_net(bid, subcmd, domain))


@bp.route("/<bid>/inject/net/<subcmd>", methods=["POST"])
def inject_net(bid, subcmd):
    valid = ["computers", "dclist", "domainControllers", "domainTrusts", "group",
             "localGroup", "logons", "sessions", "share", "time", "user", "view"]
    if subcmd not in valid:
        return jsonify({"success": False, "error": f"Invalid subcmd. Valid: {', '.join(valid)}"}), 400
    data = request.json or {}
    if not data.get("pid") or not data.get("arch"):
        return jsonify({"success": False, "error": "pid and arch required"}), 400
    return jsonify(beacon_service.inject_net(bid, data["pid"], data["arch"], subcmd, data.get("domain", "")))


@bp.route("/<bid>/spawn/net/user/detail", methods=["POST"])
def spawn_net_user_detail(bid):
    data = request.json or {}
    return jsonify(beacon_service.spawn_net_user_detail(bid, data.get("domain", ""), data.get("user", "")))


@bp.route("/<bid>/inject/net/user/detail", methods=["POST"])
def inject_net_user_detail(bid):
    data = request.json or {}
    if not data.get("pid") or not data.get("arch"):
        return jsonify({"success": False, "error": "pid and arch required"}), 400
    return jsonify(beacon_service.inject_net_user_detail(bid, data["pid"], data["arch"],
                                                         data.get("domain", ""), data.get("user", "")))


@bp.route("/<bid>/net/domain", methods=["POST"])
def net_domain(bid):
    return jsonify(beacon_service.net_domain(bid))


# ── Pivoting: link, unlink, SSH, browser pivot ──
@bp.route("/<bid>/link/smb", methods=["POST"])
def link_smb(bid):
    target = (request.json or {}).get("target", "")
    if not target:
        return jsonify({"success": False, "error": "target required"}), 400
    return jsonify(beacon_service.link_smb(bid, target, (request.json or {}).get("pipe", "")))


@bp.route("/<bid>/link/tcp", methods=["POST"])
def link_tcp(bid):
    data = request.json or {}
    if not data.get("target") or not data.get("port"):
        return jsonify({"success": False, "error": "target and port required"}), 400
    return jsonify(beacon_service.link_tcp(bid, data["target"], data["port"]))


@bp.route("/<bid>/unlink", methods=["POST"])
def unlink_beacon(bid):
    host = (request.json or {}).get("host", "")
    if not host:
        return jsonify({"success": False, "error": "host required"}), 400
    return jsonify(beacon_service.unlink(bid, host, (request.json or {}).get("pid")))


@bp.route("/<bid>/spawn/ssh", methods=["POST"])
def spawn_ssh(bid):
    data = request.json or {}
    for f in ["target", "username", "password"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.spawn_ssh(bid, data["target"], data["username"], data["password"]))


@bp.route("/<bid>/inject/ssh", methods=["POST"])
def inject_ssh(bid):
    data = request.json or {}
    for f in ["pid", "arch", "target", "username", "password"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.inject_ssh(bid, data["pid"], data["arch"], data["target"], data["username"], data["password"]))


@bp.route("/<bid>/spawn/ssh-key", methods=["POST"])
def spawn_ssh_key(bid):
    data = request.json or {}
    for f in ["target", "username", "key"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.spawn_ssh_key(bid, data["target"], data["username"], data["key"]))


@bp.route("/<bid>/inject/ssh-key", methods=["POST"])
def inject_ssh_key(bid):
    data = request.json or {}
    for f in ["pid", "arch", "target", "username", "key"]:
        if not data.get(f):
            return jsonify({"success": False, "error": f"{f} required"}), 400
    return jsonify(beacon_service.inject_ssh_key(bid, data["pid"], data["arch"], data["target"], data["username"], data["key"]))


@bp.route("/<bid>/browserpivot/start", methods=["POST"])
def browser_pivot_start(bid):
    data = request.json or {}
    if not data.get("pid") or not data.get("arch"):
        return jsonify({"success": False, "error": "pid and arch required"}), 400
    return jsonify(beacon_service.browser_pivot_start(bid, data["pid"], data["arch"]))


@bp.route("/<bid>/browserpivot/stop", methods=["POST"])
def browser_pivot_stop(bid):
    return jsonify(beacon_service.browser_pivot_stop(bid))


# ── Capture: clipboard ──
@bp.route("/<bid>/clipboard", methods=["POST"])
def get_clipboard(bid):
    return jsonify(beacon_service.get_clipboard(bid))


# ── Console: help ──
@bp.route("/<bid>/help", methods=["GET"])
def beacon_help(bid):
    return jsonify(beacon_service.get_help(bid))


@bp.route("/<bid>/help/<command>", methods=["GET"])
def beacon_command_help(bid, command):
    return jsonify(beacon_service.get_command_help(bid, command))


# ── Tasks: log/error ──
@bp.route("/task/<task_id>/log", methods=["POST"])
def task_log(task_id):
    msg = (request.json or {}).get("message", "")
    if not msg:
        return jsonify({"success": False, "error": "message required"}), 400
    return jsonify(beacon_service.log_task_message(task_id, msg))


@bp.route("/task/<task_id>/error", methods=["POST"])
def task_error(task_id):
    msg = (request.json or {}).get("message", "")
    if not msg:
        return jsonify({"success": False, "error": "message required"}), 400
    return jsonify(beacon_service.log_task_error(task_id, msg))


# ── Config: spawnto reset, argue list/remove ──
@bp.route("/<bid>/config/spawnto", methods=["DELETE"])
def config_spawnto_reset(bid):
    return jsonify(beacon_service.reset_spawnto(bid))


@bp.route("/<bid>/config/argue", methods=["GET"])
def config_argue_list(bid):
    return jsonify(beacon_service.list_spoofed_arguments(bid))


@bp.route("/<bid>/config/argue", methods=["DELETE"])
def config_argue_remove(bid):
    command = (request.json or {}).get("command", "")
    if not command:
        return jsonify({"success": False, "error": "command required"}), 400
    return jsonify(beacon_service.remove_spoofed_arguments(bid, command))


# ── Downloads data CRUD ──
@bp.route("/data/downloads/<download_id>", methods=["GET"])
def download_get(download_id):
    return jsonify(beacon_service.get_download_data(download_id))


@bp.route("/data/downloads/<download_id>", methods=["DELETE"])
def download_delete(download_id):
    return jsonify(beacon_service.delete_download_data(download_id))
