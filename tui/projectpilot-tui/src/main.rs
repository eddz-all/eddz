use crossterm::{
    cursor::{Hide, MoveTo, Show},
    execute,
    style::{Attribute, Color, ResetColor, SetAttribute, SetForegroundColor},
    terminal::{size, Clear, ClearType, EnterAlternateScreen, LeaveAlternateScreen},
};
use base64::{engine::general_purpose, Engine as _};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    env,
    fs,
    io::{self, Read, Write},
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const CAPABILITIES: &[&str] = &[
    "run_script",
    "apply_script",
    "execute_script",
    "run_remote_script",
    "apply_remote_script",
    "execute_remote_script",
];

#[derive(Debug, Clone)]
struct Config {
    server_url: String,
    token: String,
    executor_id: String,
    interval_secs: u64,
    once: bool,
    editor: String,
    execution_mode: ExecutionMode,
}

#[derive(Debug, Deserialize)]
struct PollResponse {
    task: Option<Task>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct Task {
    id: String,
    #[serde(rename = "type")]
    task_type: String,
    #[serde(default)]
    ssh_host: Option<String>,
    #[serde(default)]
    host: Option<String>,
    #[serde(default)]
    server: Option<String>,
    #[serde(default)]
    project_path: Option<String>,
    #[serde(default)]
    interpreter: Option<String>,
    #[serde(default)]
    script: Option<String>,
    #[serde(default)]
    script_content: Option<String>,
    #[serde(default)]
    script_body: Option<String>,
    #[serde(default)]
    script_base64: Option<String>,
    #[serde(default)]
    script_sha256: Option<String>,
    #[serde(default)]
    expected_sha256: Option<String>,
    #[serde(default)]
    params: Option<Value>,
    #[serde(default)]
    args: Option<Vec<String>>,
    #[serde(default)]
    env: Option<Value>,
}

#[derive(Debug)]
struct ScriptRunResult {
    success: bool,
    execution_mode: ExecutionMode,
    ssh_auth_mode: Option<SshAuthMode>,
    command: String,
    stdout: String,
    stderr: String,
    exit_code: i32,
    duration_ms: u128,
}

#[derive(Debug, Clone, Copy)]
enum ExecutionMode {
    Local,
    Ssh,
}

impl ExecutionMode {
    fn as_str(self) -> &'static str {
        match self {
            ExecutionMode::Local => "local",
            ExecutionMode::Ssh => "ssh",
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum SshAuthMode {
    KeyOnly,
    Password,
}

impl SshAuthMode {
    fn as_str(self) -> &'static str {
        match self {
            SshAuthMode::KeyOnly => "key",
            SshAuthMode::Password => "password",
        }
    }
}

struct ScreenGuard;

impl ScreenGuard {
    fn enter() -> Result<Self, String> {
        let mut stdout = io::stdout();
        execute!(stdout, EnterAlternateScreen, Hide, MoveTo(0, 0), Clear(ClearType::All))
            .map_err(|err| format!("failed to enter terminal screen: {err}"))?;
        Ok(Self)
    }
}

impl Drop for ScreenGuard {
    fn drop(&mut self) {
        let mut stdout = io::stdout();
        let _ = execute!(stdout, Show, LeaveAlternateScreen);
    }
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        print_usage();
        return;
    }

    let config = match Config::from_args(args) {
        Ok(config) => config,
        Err(message) => {
            eprintln!("{message}");
            print_usage();
            std::process::exit(2);
        }
    };

    if let Err(err) = run(config) {
        eprintln!("projectpilot-tui: {err}");
        std::process::exit(1);
    }
}

fn run(config: Config) -> Result<(), String> {
    let _screen = ScreenGuard::enter()?;
    loop {
        draw_idle(&config);

        match poll_task(&config)? {
            Some(task) => handle_task(&config, task)?,
            None => {
                if config.once {
                    print_status_line("No pending script task.", Color::DarkGrey);
                    return Ok(());
                }
                print_status_line(
                    &format!("No pending script task. Polling again in {}s. Press Ctrl+C to stop.", config.interval_secs),
                    Color::DarkGrey,
                );
                std::thread::sleep(Duration::from_secs(config.interval_secs));
            }
        }

        if config.once {
            return Ok(());
        }
    }
}

fn handle_task(config: &Config, task: Task) -> Result<(), String> {
    if !CAPABILITIES.contains(&task.task_type.as_str()) {
        submit_rejection(config, &task, "unsupported_task", "TUI only handles script tasks.")?;
        return Ok(());
    }

    let host = task.ssh_host.clone().or(task.host.clone()).or(task.server.clone());
    if matches!(config.execution_mode, ExecutionMode::Ssh) && host.is_none() {
        return Err("Task is missing ssh_host/host/server for SSH execution mode.".to_string());
    }
    let project_path = task
        .project_path
        .clone()
        .ok_or_else(|| "Task is missing project_path.".to_string())?;
    let original_script = extract_script(&task)?;
    let expected_hash = task
        .script_sha256
        .clone()
        .or(task.expected_sha256.clone());

    let mut script = original_script.clone();
    loop {
        draw_task(
            config,
            &task,
            config.execution_mode,
            host.as_deref(),
            &project_path,
            &script,
            expected_hash.as_deref(),
        )?;
        println!();
        draw_action_bar(config.execution_mode);
        print!("Choice: ");
        flush_stdout()?;

        let choice = read_line()?.to_lowercase();
        match choice.trim() {
            "a" | "approve" | "key" => {
                let ssh_auth_mode = if matches!(config.execution_mode, ExecutionMode::Ssh) {
                    Some(SshAuthMode::KeyOnly)
                } else {
                    None
                };
                match execute_script_task(
                    &task,
                    config.execution_mode,
                    host.as_deref(),
                    &project_path,
                    &script,
                    ssh_auth_mode,
                ) {
                    Ok(result) => {
                        draw_run_result(&result);
                        submit_script_result(config, &task, &original_script, &script, &result)?;
                    }
                    Err(err) => {
                        draw_error("Execution Error", &err);
                        submit_rejection(config, &task, "executor_error", &err)?;
                    }
                }
                pause()?;
                return Ok(());
            }
            "p" | "password" => {
                if !matches!(config.execution_mode, ExecutionMode::Ssh) {
                    println!("Password mode is only available with --execution-mode ssh.");
                    pause()?;
                    continue;
                }
                let host = host.as_deref().ok_or("Task is missing ssh_host/host/server.")?;
                println!("Password mode selected. If SSH prompts, enter the password for {host} in this terminal.");
                flush_stdout()?;
                match execute_script_task(
                    &task,
                    config.execution_mode,
                    Some(host),
                    &project_path,
                    &script,
                    Some(SshAuthMode::Password),
                ) {
                    Ok(result) => {
                        draw_run_result(&result);
                        submit_script_result(config, &task, &original_script, &script, &result)?;
                    }
                    Err(err) => {
                        draw_error("Execution Error", &err);
                        submit_rejection(config, &task, "executor_error", &err)?;
                    }
                }
                pause()?;
                return Ok(());
            }
            "e" | "edit" => {
                script = edit_script(&config.editor, &script)?;
            }
            "r" | "reject" => {
                print!("Reject reason: ");
                flush_stdout()?;
                let reason = read_line()?;
                submit_rejection(config, &task, "user_rejected", reason.trim())?;
                return Ok(());
            }
            "q" | "quit" => return Ok(()),
            _ => {
                println!("Unknown choice.");
                pause()?;
            }
        }
    }
}

fn poll_task(config: &Config) -> Result<Option<Task>, String> {
    let payload = json!({
        "executor_id": config.executor_id.clone(),
        "mode": "tui",
        "capabilities": CAPABILITIES,
        "status": "online"
    });
    let response: PollResponse = post_json(config, "/executor/poll", payload)?;
    Ok(response.task)
}

fn execute_script_task(
    task: &Task,
    execution_mode: ExecutionMode,
    host: Option<&str>,
    project_path: &str,
    script: &str,
    ssh_auth_mode: Option<SshAuthMode>,
) -> Result<ScriptRunResult, String> {
    validate_remote_path(project_path)?;
    let interpreter = task.interpreter.as_deref().unwrap_or("bash");
    if interpreter != "bash" && interpreter != "sh" {
        return Err(format!("Unsupported interpreter: {interpreter}"));
    }
    let args = task_args(task)?;
    let env_vars = task_env(task)?;
    let command = build_remote_command(project_path, interpreter, &args, &env_vars);

    let started = Instant::now();
    let mut process = match execution_mode {
        ExecutionMode::Local => {
            let mut local = Command::new("sh");
            local
                .arg("-lc")
                .arg(&command)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|err| format!("failed to start local shell: {err}"))?
        }
        ExecutionMode::Ssh => {
            let host = host.ok_or("Task is missing ssh_host/host/server.")?;
            let auth_mode = ssh_auth_mode.unwrap_or(SshAuthMode::KeyOnly);
            let mut ssh = Command::new("ssh");
            ssh.arg("-o").arg("ConnectTimeout=8");
            match auth_mode {
                SshAuthMode::KeyOnly => {
                    ssh.arg("-o").arg("BatchMode=yes");
                }
                SshAuthMode::Password => {
                    ssh.arg("-o").arg("BatchMode=no");
                    ssh.arg("-o").arg("NumberOfPasswordPrompts=3");
                }
            }
            ssh.arg(host)
                .arg(&command)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|err| format!("failed to start ssh: {err}"))?
        }
    };

    {
        let stdin = process.stdin.as_mut().ok_or("failed to open process stdin")?;
        stdin
            .write_all(normalize_script(script).as_bytes())
            .map_err(|err| format!("failed to write script to process stdin: {err}"))?;
    }

    let output = process
        .wait_with_output()
        .map_err(|err| format!("failed to wait for process: {err}"))?;
    let exit_code = output.status.code().unwrap_or(-1);
    Ok(ScriptRunResult {
        success: output.status.success(),
        execution_mode,
        ssh_auth_mode,
        command,
        stdout: String::from_utf8_lossy(&output.stdout).to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        exit_code,
        duration_ms: started.elapsed().as_millis(),
    })
}

fn submit_script_result(
    config: &Config,
    task: &Task,
    original_script: &str,
    final_script: &str,
    run: &ScriptRunResult,
) -> Result<(), String> {
    let original_hash = sha256_hex(&normalize_script(original_script));
    let final_hash = sha256_hex(&normalize_script(final_script));
    let payload = json!({
        "task_id": task.id.clone(),
        "executor_id": config.executor_id.clone(),
        "success": run.success,
        "error_type": if run.success { Value::Null } else { json!("remote_script_failed") },
        "message": if run.success { "Script executed successfully" } else { "Remote script failed" },
        "started_at": now_string(),
        "finished_at": now_string(),
        "duration_ms": run.duration_ms,
        "result": {
            "success": run.success,
            "task_id": task.id.clone(),
            "task_type": task.task_type.clone(),
            "operation": if matches!(run.execution_mode, ExecutionMode::Local) { "run_script" } else { "run_remote_script" },
            "execution_mode": run.execution_mode.as_str(),
            "ssh_auth_mode": run.ssh_auth_mode.map(|mode| mode.as_str()),
            "ssh_host": task.ssh_host.clone().or(task.host.clone()).or(task.server.clone()),
            "project_path": task.project_path.clone(),
            "command": run.command,
            "stdout": run.stdout,
            "stderr": run.stderr,
            "exit_code": run.exit_code,
            "script_sha256": final_hash,
            "original_script_sha256": original_hash,
            "script_modified": original_hash != final_hash,
            "script_size": normalize_script(final_script).as_bytes().len(),
            "approved_by": "projectpilot-tui"
        }
    });
    let _: Value = post_json(config, &format!("/executor/tasks/{}/result", task.id), payload)?;
    Ok(())
}

fn submit_rejection(config: &Config, task: &Task, error_type: &str, reason: &str) -> Result<(), String> {
    let payload = json!({
        "task_id": task.id.clone(),
        "executor_id": config.executor_id.clone(),
        "success": false,
        "error_type": error_type,
        "message": reason,
        "started_at": now_string(),
        "finished_at": now_string(),
        "duration_ms": 0,
        "result": {
            "success": false,
            "task_id": task.id.clone(),
            "task_type": task.task_type.clone(),
            "error_type": error_type,
            "message": reason,
            "approved_by": "projectpilot-tui"
        }
    });
    let _: Value = post_json(config, &format!("/executor/tasks/{}/result", task.id), payload)?;
    Ok(())
}

fn post_json<T: for<'de> Deserialize<'de>>(
    config: &Config,
    path: &str,
    payload: Value,
) -> Result<T, String> {
    let url = format!("{}{}", config.server_url.trim_end_matches('/'), path);
    let response = ureq::post(&url)
        .set("Authorization", &format!("Bearer {}", config.token))
        .set("Content-Type", "application/json")
        .send_string(&payload.to_string())
        .map_err(|err| format!("HTTP request failed for {url}: {err}"))?;
    response
        .into_json::<T>()
        .map_err(|err| format!("invalid JSON response from {url}: {err}"))
}

fn draw_idle(config: &Config) {
    draw_header("Waiting for Tasks");
    print_panel(
        "Connection",
        &[
            kv_line("Backend", &config.server_url),
            kv_line("Executor", &config.executor_id),
            kv_line("Mode", config.execution_mode.as_str()),
            kv_line("Poll Interval", &format!("{}s", config.interval_secs)),
        ],
    );
    println!();
    print_status_line("Agent online. Waiting for a backend task.", Color::Green);
}

fn draw_header(title: &str) {
    let mut stdout = io::stdout();
    let _ = execute!(
        stdout,
        MoveTo(0, 0),
        Clear(ClearType::All),
        SetForegroundColor(Color::Cyan),
        SetAttribute(Attribute::Bold)
    );
    println!("ProjectPilot Agent TUI");
    let _ = execute!(stdout, ResetColor, SetAttribute(Attribute::Reset));
    print_status_line(title, Color::White);
    print_rule_with('=');
}

fn draw_task(
    _config: &Config,
    task: &Task,
    execution_mode: ExecutionMode,
    host: Option<&str>,
    project_path: &str,
    script: &str,
    expected_hash: Option<&str>,
) -> Result<(), String> {
    draw_header("Pending Script");
    let actual_hash = sha256_hex(&normalize_script(script));
    let normalized = normalize_script(script);
    let target = match (execution_mode, host) {
        (ExecutionMode::Local, _) => "local".to_string(),
        (ExecutionMode::Ssh, Some(host)) => format!("ssh:{host}"),
        (ExecutionMode::Ssh, None) => "ssh".to_string(),
    };
    let hash_label = if let Some(hash) = expected_hash {
        format!(
            "{} ({})",
            short_hash(&actual_hash),
            if hash == actual_hash { "match" } else { "mismatch" }
        )
    } else {
        format!("{} (no expected hash)", short_hash(&actual_hash))
    };
    let task_lines = vec![
        kv_line("Task", &format!("{} ({})", task.id, task.task_type)),
        kv_line("Target", &target),
        kv_line("Project", project_path),
        kv_line(
            "Script",
            &format!(
                "{} lines, {} bytes, {}",
                script_line_count(script),
                normalized.as_bytes().len(),
                task.interpreter.as_deref().unwrap_or("bash")
            ),
        ),
        kv_line("SHA256", &hash_label),
    ];
    print_panel("Review", &task_lines);
    println!();
    print_section_title("Script Preview");
    print_numbered_limited(script, task_preview_lines());
    Ok(())
}

fn draw_run_result(result: &ScriptRunResult) {
    draw_header("Script Result");
    let mut summary = vec![
        kv_line("Status", if result.success { "success" } else { "failed" }),
        kv_line("Execution", result.execution_mode.as_str()),
        kv_line("Exit Code", &result.exit_code.to_string()),
        kv_line("Duration", &format!("{} ms", result.duration_ms)),
        kv_line("Command", &result.command),
    ];
    if let Some(auth_mode) = result.ssh_auth_mode {
        summary.push(kv_line("SSH Auth", auth_mode.as_str()));
    }
    print_panel("Summary", &summary);
    println!();
    let preview_lines = result_preview_lines();
    let stdout_lines = if result.stderr.trim().is_empty() {
        preview_lines
    } else {
        (preview_lines / 2).max(2)
    };
    let stderr_lines = preview_lines.saturating_sub(stdout_lines).max(2);
    print_section_title("Stdout");
    print_trimmed_block(&result.stdout, stdout_lines);
    if !result.stderr.trim().is_empty() || !result.success {
        println!();
        print_section_title("Stderr");
        print_trimmed_block(&result.stderr, stderr_lines);
    }
}

fn draw_error(title: &str, message: &str) {
    draw_header(title);
    print_status_line(message, Color::Red);
}

fn kv_line(label: &str, value: &str) -> String {
    format!("{:<14} {}", label, truncate_text(value, content_width().saturating_sub(17)))
}

fn print_rule() {
    print_rule_with('-');
}

fn print_rule_with(ch: char) {
    let mut stdout = io::stdout();
    let _ = execute!(stdout, SetForegroundColor(Color::DarkGrey));
    println!("{}", ch.to_string().repeat(content_width()));
    let _ = execute!(stdout, ResetColor);
}

fn print_panel(title: &str, lines: &[String]) {
    let width = content_width();
    let border_inner = width.saturating_sub(2);
    let content_inner = width.saturating_sub(4);
    let title_text = format!(" {} ", title);
    let title_len = title_text.chars().count();
    let right = border_inner.saturating_sub(title_len);
    let mut stdout = io::stdout();
    let _ = execute!(stdout, SetForegroundColor(Color::DarkGrey));
    print!("+");
    let _ = execute!(stdout, SetForegroundColor(Color::Cyan), SetAttribute(Attribute::Bold));
    print!("{title_text}");
    let _ = execute!(stdout, SetForegroundColor(Color::DarkGrey), SetAttribute(Attribute::Reset));
    println!("{}+", "-".repeat(right));
    for line in lines {
        let text = truncate_text(line, content_inner);
        println!(
            "| {}{} |",
            text,
            " ".repeat(content_inner.saturating_sub(text.chars().count()))
        );
    }
    println!("+{}+", "-".repeat(border_inner));
    let _ = execute!(stdout, ResetColor);
}

fn print_section_title(title: &str) {
    let mut stdout = io::stdout();
    let _ = execute!(stdout, SetForegroundColor(Color::Cyan), SetAttribute(Attribute::Bold));
    println!("{title}");
    let _ = execute!(stdout, ResetColor, SetAttribute(Attribute::Reset));
    print_rule();
}

fn print_status_line(message: &str, color: Color) {
    let mut stdout = io::stdout();
    let _ = execute!(stdout, SetForegroundColor(color));
    println!("{}", truncate_text(message, content_width()));
    let _ = execute!(stdout, ResetColor);
}

fn draw_action_bar(mode: ExecutionMode) {
    print_section_title("Actions");
    match mode {
        ExecutionMode::Local => {
            print_key("a", "approve and execute locally");
            print!("   ");
            print_key("e", "edit script");
            print!("   ");
            print_key("r", "reject");
            print!("   ");
            print_key("q", "quit");
            println!();
        }
        ExecutionMode::Ssh => {
            print_key("a", "approve with key/agent");
            print!("   ");
            print_key("p", "approve with password");
            print!("   ");
            print_key("e", "edit script");
            print!("   ");
            print_key("r", "reject");
            print!("   ");
            print_key("q", "quit");
            println!();
        }
    }
}

fn print_key(key: &str, label: &str) {
    let mut stdout = io::stdout();
    let _ = execute!(stdout, SetForegroundColor(Color::Yellow), SetAttribute(Attribute::Bold));
    print!("[{key}]");
    let _ = execute!(stdout, ResetColor, SetAttribute(Attribute::Reset));
    print!(" {label}");
}

fn content_width() -> usize {
    let width = size().map(|(width, _)| width as usize).unwrap_or(96);
    if width < 40 {
        width.saturating_sub(1).max(10)
    } else {
        width.saturating_sub(1).min(120)
    }
}

fn terminal_height() -> usize {
    size().map(|(_, height)| height as usize).unwrap_or(24).max(16)
}

fn task_preview_lines() -> usize {
    terminal_height().saturating_sub(18).clamp(3, 10)
}

fn result_preview_lines() -> usize {
    terminal_height().saturating_sub(17).clamp(4, 14)
}

fn truncate_text(value: &str, max_chars: usize) -> String {
    if max_chars == 0 {
        return String::new();
    }
    let mut output = String::new();
    let mut count = 0;
    for ch in value.chars() {
        if count + 1 >= max_chars {
            output.push('~');
            return output;
        }
        output.push(ch);
        count += 1;
    }
    output
}

fn edit_script(editor: &str, script: &str) -> Result<String, String> {
    let path = temp_script_path();
    fs::write(&path, normalize_script(script)).map_err(|err| format!("failed to write temp script: {err}"))?;
    let status = Command::new(editor)
        .arg(&path)
        .status()
        .map_err(|err| format!("failed to open editor {editor}: {err}"))?;
    if !status.success() {
        return Err(format!("editor exited with status {status}"));
    }
    let mut edited = String::new();
    fs::File::open(&path)
        .map_err(|err| format!("failed to open edited script: {err}"))?
        .read_to_string(&mut edited)
        .map_err(|err| format!("failed to read edited script: {err}"))?;
    let _ = fs::remove_file(&path);
    Ok(edited)
}

fn print_numbered_limited(text: &str, max_lines: usize) {
    let width = content_width().saturating_sub(8).max(32);
    let total = script_line_count(text);
    for (index, line) in text.lines().take(max_lines).enumerate() {
        println!("{:>4} | {}", index + 1, truncate_text(line, width));
    }
    if total > max_lines {
        println!(
            "     | ... {} more lines (press e for full script).",
            total - max_lines
        );
    }
}

fn print_trimmed_block(text: &str, max_lines: usize) {
    if text.trim().is_empty() {
        println!("(empty)");
        return;
    }
    let width = content_width();
    let total = text.lines().count();
    for line in text.lines().take(max_lines) {
        println!("{}", truncate_text(line, width));
    }
    if total > max_lines {
        println!("... {} more lines truncated ...", total - max_lines);
    }
}

fn script_line_count(text: &str) -> usize {
    let count = text.lines().count();
    if count == 0 { 1 } else { count }
}

fn short_hash(value: &str) -> String {
    let total = value.chars().count();
    if total <= 20 {
        return value.to_string();
    }
    let prefix: String = value.chars().take(10).collect();
    let suffix: String = value
        .chars()
        .skip(total.saturating_sub(6))
        .collect();
    format!("{prefix}...{suffix}")
}

fn extract_script(task: &Task) -> Result<String, String> {
    if let Some(script) = task
        .script
        .clone()
        .or(task.script_content.clone())
        .or(task.script_body.clone())
    {
        return Ok(script);
    }
    if let Some(encoded) = &task.script_base64 {
        let bytes = general_purpose::STANDARD
            .decode(encoded)
            .map_err(|err| format!("script_base64 is invalid: {err}"))?;
        return String::from_utf8(bytes).map_err(|err| format!("script_base64 is not UTF-8: {err}"));
    }
    Err("Task is missing script/script_content/script_body/script_base64.".to_string())
}

fn task_args(task: &Task) -> Result<Vec<String>, String> {
    if let Some(args) = &task.args {
        return Ok(args.clone());
    }
    if let Some(Value::Object(params)) = &task.params {
        if let Some(Value::Array(args)) = params.get("args") {
            return Ok(args.iter().map(value_to_string).collect());
        }
    }
    Ok(Vec::new())
}

fn task_env(task: &Task) -> Result<Vec<(String, String)>, String> {
    if let Some(env) = &task.env {
        return parse_env_value(env);
    }
    if let Some(Value::Object(params)) = &task.params {
        if let Some(env) = params.get("env") {
            return parse_env_value(env);
        }
    }
    Ok(Vec::new())
}

fn parse_env_value(value: &Value) -> Result<Vec<(String, String)>, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "env must be a JSON object.".to_string())?;
    let mut env = Vec::new();
    for (key, value) in object {
        validate_env_key(key)?;
        env.push((key.clone(), value_to_string(value)));
    }
    Ok(env)
}

fn build_remote_command(
    project_path: &str,
    interpreter: &str,
    args: &[String],
    env_vars: &[(String, String)],
) -> String {
    let mut command = String::new();
    if !env_vars.is_empty() {
        command.push_str("env ");
        for (key, value) in env_vars {
            command.push_str(key);
            command.push('=');
            command.push_str(&shell_quote(value));
            command.push(' ');
        }
    }
    command.push_str(&shell_quote(interpreter));
    command.push_str(" -s --");
    for arg in args {
        command.push(' ');
        command.push_str(&shell_quote(arg));
    }
    format!("cd {} && {}", shell_quote(project_path), command)
}

fn validate_remote_path(project_path: &str) -> Result<(), String> {
    if !project_path.starts_with('/') {
        return Err("project_path must be an absolute remote path.".to_string());
    }
    if project_path.contains('\0') || project_path.contains('\n') || project_path.contains('\r') {
        return Err("project_path contains invalid characters.".to_string());
    }
    Ok(())
}

fn validate_env_key(key: &str) -> Result<(), String> {
    let mut chars = key.chars();
    let Some(first) = chars.next() else {
        return Err("environment variable name is empty.".to_string());
    };
    if first.is_ascii_digit() {
        return Err(format!("invalid environment variable name: {key}"));
    }
    if !key.chars().all(|ch| ch.is_ascii_alphanumeric() || ch == '_') {
        return Err(format!("invalid environment variable name: {key}"));
    }
    Ok(())
}

fn shell_quote(value: &str) -> String {
    if value.is_empty() {
        return "''".to_string();
    }
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || "-_./:=@".contains(ch))
    {
        return value.to_string();
    }
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn normalize_script(script: &str) -> String {
    let mut text = script.to_string();
    if !text.ends_with('\n') {
        text.push('\n');
    }
    text
}

fn sha256_hex(value: &str) -> String {
    hex::encode(Sha256::digest(value.as_bytes()))
}

fn value_to_string(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn temp_script_path() -> PathBuf {
    let mut path = env::temp_dir();
    path.push(format!("projectpilot-script-{}.sh", now_millis()));
    path
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn now_string() -> String {
    now_millis().to_string()
}

fn read_line() -> Result<String, String> {
    let mut line = String::new();
    io::stdin()
        .read_line(&mut line)
        .map_err(|err| format!("failed to read input: {err}"))?;
    Ok(line)
}

fn flush_stdout() -> Result<(), String> {
    io::stdout()
        .flush()
        .map_err(|err| format!("failed to flush stdout: {err}"))
}

fn pause() -> Result<(), String> {
    println!("Press Enter to continue.");
    let _ = read_line()?;
    Ok(())
}

fn print_usage() {
    eprintln!(
        "Usage: projectpilot-tui --server-url URL --token TOKEN --executor-id ID [--once] [--interval SECONDS] [--editor EDITOR] [--execution-mode local|ssh]"
    );
}

impl Config {
    fn from_args(args: Vec<String>) -> Result<Self, String> {
        let mut server_url = env::var("PROJECTPILOT_SERVER_URL").ok();
        let mut token = env::var("PROJECTPILOT_EXECUTOR_TOKEN").ok();
        let mut executor_id = env::var("PROJECTPILOT_EXECUTOR_ID").unwrap_or_else(|_| "projectpilot-tui".to_string());
        let mut interval_secs = 5;
        let mut once = false;
        let mut editor = env::var("EDITOR").unwrap_or_else(|_| "vi".to_string());
        let mut execution_mode = env::var("PROJECTPILOT_EXECUTION_MODE")
            .ok()
            .map(|value| parse_execution_mode(&value))
            .transpose()?
            .unwrap_or(ExecutionMode::Local);

        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--server-url" => {
                    index += 1;
                    server_url = args.get(index).cloned();
                }
                "--token" => {
                    index += 1;
                    token = args.get(index).cloned();
                }
                "--executor-id" => {
                    index += 1;
                    executor_id = args
                        .get(index)
                        .cloned()
                        .ok_or_else(|| "--executor-id requires a value".to_string())?;
                }
                "--interval" => {
                    index += 1;
                    interval_secs = args
                        .get(index)
                        .ok_or_else(|| "--interval requires a value".to_string())?
                        .parse::<u64>()
                        .map_err(|_| "--interval must be an integer".to_string())?;
                }
                "--editor" => {
                    index += 1;
                    editor = args
                        .get(index)
                        .cloned()
                        .ok_or_else(|| "--editor requires a value".to_string())?;
                }
                "--execution-mode" => {
                    index += 1;
                    execution_mode = parse_execution_mode(
                        args.get(index)
                            .ok_or_else(|| "--execution-mode requires a value".to_string())?,
                    )?;
                }
                "--once" => once = true,
                unknown => return Err(format!("unknown argument: {unknown}")),
            }
            index += 1;
        }

        Ok(Self {
            server_url: server_url
                .ok_or_else(|| "--server-url or PROJECTPILOT_SERVER_URL is required".to_string())?,
            token: token.ok_or_else(|| "--token or PROJECTPILOT_EXECUTOR_TOKEN is required".to_string())?,
            executor_id,
            interval_secs,
            once,
            editor,
            execution_mode,
        })
    }
}

fn parse_execution_mode(value: &str) -> Result<ExecutionMode, String> {
    match value.trim().to_lowercase().as_str() {
        "local" | "server" | "host" => Ok(ExecutionMode::Local),
        "ssh" | "remote" => Ok(ExecutionMode::Ssh),
        other => Err(format!("unsupported execution mode: {other}")),
    }
}
