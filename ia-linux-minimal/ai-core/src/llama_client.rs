//! Cliente HTTP mínimo para `/completion` do `llama-server` (ver
//! rootfs-overlay/usr/bin/ia-server — mesmo processo que `ia-server
//! start` gerencia, escutando em 127.0.0.1:8080 por padrão).
//!
//! Implementado sobre `std::net::TcpStream` (sem dependências externas —
//! ver justificativa em json.rs) em vez de um cliente HTTP completo:
//! monta a requisição à mão, lê a resposta inteira e separa cabeçalho de
//! corpo em `\r\n\r\n`.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use crate::json;

const READ_TIMEOUT: Duration = Duration::from_secs(120);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);

/// Envia `prompt` a `addr` (ex.: "127.0.0.1:8080") via `POST /completion`
/// e retorna o campo `content` da resposta. `n_predict` limita o número
/// de tokens gerados.
pub fn complete(addr: &str, prompt: &str, n_predict: u32) -> Result<String, String> {
    let socket_addr = addr
        .parse()
        .map_err(|e| format!("endereço inválido '{addr}': {e}"))?;

    let mut stream = TcpStream::connect_timeout(&socket_addr, CONNECT_TIMEOUT)
        .map_err(|e| format!("não foi possível conectar a {addr}: {e}"))?;
    stream
        .set_read_timeout(Some(READ_TIMEOUT))
        .map_err(|e| format!("falha ao configurar timeout: {e}"))?;

    let body = format!(
        r#"{{"prompt":{},"n_predict":{n_predict}}}"#,
        json::quote(prompt)
    );
    let request = format!(
        "POST /completion HTTP/1.1\r\n\
         Host: {addr}\r\n\
         Content-Type: application/json\r\n\
         Content-Length: {}\r\n\
         Connection: close\r\n\
         \r\n\
         {body}",
        body.len()
    );

    stream
        .write_all(request.as_bytes())
        .map_err(|e| format!("falha ao enviar requisição: {e}"))?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|e| format!("falha ao ler resposta: {e}"))?;

    let response_body = split_http_body(&response).ok_or_else(|| {
        format!("resposta HTTP sem corpo separado por linha em branco: {response}")
    })?;

    json::extract_string_field(response_body, "content").ok_or_else(|| {
        format!("campo 'content' ausente na resposta de {addr}/completion: {response_body}")
    })
}

fn split_http_body(response: &str) -> Option<&str> {
    let idx = response.find("\r\n\r\n")?;
    Some(&response[idx + 4..])
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::BufRead;
    use std::net::TcpListener;
    use std::thread;

    /// Sobe um servidor HTTP de mentira em 127.0.0.1:0 (porta escolhida
    /// pelo SO), atende exatamente uma conexão, descarta a requisição e
    /// responde com `response_body` bruto (já incluindo cabeçalhos).
    fn spawn_mock_server(raw_response: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap().to_string();

        thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut reader = std::io::BufReader::new(stream.try_clone().unwrap());
                let mut line = String::new();
                // consome só a linha de requisição; não precisamos validar o corpo
                let _ = reader.read_line(&mut line);
                let _ = stream.write_all(raw_response.as_bytes());
            }
        });

        addr
    }

    #[test]
    fn successful_completion_extracts_content() {
        let addr = spawn_mock_server(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"content\":\"ola do mock\"}",
        );
        let result = complete(&addr, "diga oi", 16).unwrap();
        assert_eq!(result, "ola do mock");
    }

    #[test]
    fn missing_content_field_is_an_error() {
        let addr = spawn_mock_server("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{}");
        let result = complete(&addr, "diga oi", 16);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("content"));
    }

    #[test]
    fn connection_refused_is_an_error() {
        // Porta 1 é privilegiada e não deve ter nada escutando no host de
        // teste; se por acaso houver, o teste apenas não valida esse caso.
        let result = complete("127.0.0.1:1", "diga oi", 16);
        assert!(result.is_err());
    }
}
