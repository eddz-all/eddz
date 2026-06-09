#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[tauri::command]
async fn api_request(
    method: String,
    url: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let method = reqwest::Method::from_bytes(method.as_bytes())
        .map_err(|error| format!("Invalid HTTP method: {error}"))?;
    let client = reqwest::Client::new();
    let mut request = client.request(method, &url);

    if let Some(body) = body {
        request = request.json(&body);
    }

    let response = request
        .send()
        .await
        .map_err(|error| format!("API request failed: {error}"))?;
    let status = response.status();
    let text = response
        .text()
        .await
        .map_err(|error| format!("API response read failed: {error}"))?;

    if !status.is_success() {
        return Err(format!("{} {}", status.as_u16(), text));
    }

    if text.trim().is_empty() {
        return Ok(serde_json::json!({ "ok": true }));
    }

    serde_json::from_str(&text).or_else(|_| Ok(serde_json::json!({ "content": text })))
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![api_request])
        .run(tauri::generate_context!())
        .expect("error while running ProjectPilot");
}
