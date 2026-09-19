//! Servidor IPC via socket Unix. Protocolo texto simples: uma linha de
//! comando por conexão, resposta em uma ou mais linhas terminada por uma
//! linha contendo apenas `.` (estilo SMTP), conexão então é fechada pelo
//! servidor. `ia-shell` é o cliente de referência (ver
//! rootfs-overlay/usr/bin/ia-shell).

use std::io::{BufRead, BufReader, Write};
use std::net::Shutdown;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::sync::Arc;
use std::thread;

/// Lado cliente do protocolo: conecta, envia uma linha de comando, lê a
/// resposta até a linha terminadora `.` e a devolve sem ela.
pub fn query(socket_path: &str, command: &str) -> std::io::Result<Vec<String>> {
    let stream = UnixStream::connect(socket_path)?;
    let mut writer = stream.try_clone()?;
    writeln!(writer, "{command}")?;
    stream.shutdown(Shutdown::Write)?;

    let reader = BufReader::new(stream);
    let mut lines = Vec::new();
    for line in reader.lines() {
        let line = line?;
        if line == "." {
            break;
        }
        lines.push(line);
    }
    Ok(lines)
}

pub fn serve<S, F>(socket_path: &str, state: Arc<S>, dispatch: F) -> std::io::Result<()>
where
    S: Send + Sync + 'static,
    F: Fn(&str, &S) -> Vec<String> + Send + Sync + Copy + 'static,
{
    let path = Path::new(socket_path);
    if path.exists() {
        std::fs::remove_file(path)?;
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let listener = UnixListener::bind(path)?;
    eprintln!("ai-core: escutando em {socket_path}");

    for incoming in listener.incoming() {
        match incoming {
            Ok(stream) => {
                let state = Arc::clone(&state);
                thread::spawn(move || {
                    if let Err(e) = handle_client(stream, &*state, dispatch) {
                        eprintln!("ai-core: erro ao atender cliente: {e}");
                    }
                });
            }
            Err(e) => eprintln!("ai-core: erro ao aceitar conexão: {e}"),
        }
    }

    Ok(())
}

fn handle_client<S, F>(stream: UnixStream, state: &S, dispatch: F) -> std::io::Result<()>
where
    F: Fn(&str, &S) -> Vec<String>,
{
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut writer = stream;

    let mut line = String::new();
    let bytes_read = reader.read_line(&mut line)?;
    if bytes_read == 0 {
        return Ok(());
    }

    let response = dispatch(line.trim_end(), state);
    for out_line in response {
        writeln!(writer, "{out_line}")?;
    }
    writeln!(writer, ".")?;
    writer.flush()?;

    Ok(())
}
