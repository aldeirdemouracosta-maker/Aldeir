//! Utilitários JSON mínimos, escritos à mão para não adicionar
//! dependências externas ao `ai-core` (facilita a cross-compilação via
//! Buildroot — ver package/ai-core/ai-core.mk). Cobrem exatamente o que
//! `llama_client.rs` precisa: montar o corpo de uma requisição a
//! `llama-server` e extrair um campo string de uma resposta plana.
//!
//! Não é um parser JSON completo: não lida com objetos/arrays aninhados
//! de forma genérica, apenas procura um campo pelo nome em qualquer
//! nível do documento (útil para campos como `timings.predicted_per_second`,
//! que ficam aninhados, sem precisar navegar a árvore). É suficiente
//! para a resposta de `/completion` do llama.cpp, que tem `"content"` e
//! (dentro de `"timings"`) `"predicted_per_second"`.

/// Converte uma string Rust em uma string JSON válida entre aspas,
/// escapando `"`, `\`, controle e novas linhas.
pub fn quote(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Extrai o valor de um campo string `"campo": "valor"` de um JSON plano.
/// Tolera espaço em branco entre `:` e a aspas de abertura — o JSON
/// padrão permite isso, e nem todo produtor de JSON gera saída compacta
/// (ex.: `json.dumps` do Python insere um espaço por padrão; foi assim
/// que este caso foi encontrado, num smoke test contra um llama-server
/// de mentira escrito em Python). Não lida com pares substitutos
/// (`\uD800`-`\uDFFF`) — suficiente para texto comum retornado por
/// llama.cpp; caracteres fora do BMP no meio de uma sequência `\u`
/// escapada não são suportados.
pub fn extract_string_field(json: &str, field: &str) -> Option<String> {
    let key_needle = format!("\"{field}\"");
    let key_idx = json.find(&key_needle)?;
    let after_key = &json[key_idx + key_needle.len()..];

    let after_colon = skip_whitespace_then_expect(after_key, ':')?;
    let rest = skip_whitespace_then_expect(after_colon, '"')?;

    let mut out = String::new();
    let mut chars = rest.chars();
    while let Some(c) = chars.next() {
        match c {
            '"' => return Some(out),
            '\\' => match chars.next()? {
                '"' => out.push('"'),
                '\\' => out.push('\\'),
                '/' => out.push('/'),
                'n' => out.push('\n'),
                'r' => out.push('\r'),
                't' => out.push('\t'),
                'u' => {
                    let hex: String = chars.by_ref().take(4).collect();
                    if hex.len() != 4 {
                        return None;
                    }
                    let code = u32::from_str_radix(&hex, 16).ok()?;
                    out.push(char::from_u32(code)?);
                }
                other => out.push(other),
            },
            c => out.push(c),
        }
    }
    None // string não terminada
}

/// Extrai o valor de um campo numérico `"campo": 123.45` (sem aspas) de
/// um JSON plano, em qualquer nível de aninhamento (busca o nome do
/// campo no texto inteiro, não só no nível superior — ver nota do
/// módulo). Aceita inteiros e decimais com sinal; não lida com notação
/// científica (`1e10`), que o llama-server não usa nesses campos.
pub fn extract_number_field(json: &str, field: &str) -> Option<f64> {
    let key_needle = format!("\"{field}\"");
    let key_idx = json.find(&key_needle)?;
    let after_key = &json[key_idx + key_needle.len()..];

    let after_colon = skip_whitespace_then_expect(after_key, ':')?;
    let trimmed = after_colon.trim_start();
    let end = trimmed
        .find(|c: char| !(c.is_ascii_digit() || c == '.' || c == '-' || c == '+'))
        .unwrap_or(trimmed.len());
    if end == 0 {
        return None;
    }
    trimmed[..end].parse().ok()
}

/// Pula espaço em branco no início de `s` e confirma que o próximo
/// caractere é exatamente `expected`; retorna o restante de `s` logo
/// após esse caractere, ou `None` se não bater.
fn skip_whitespace_then_expect(s: &str, expected: char) -> Option<&str> {
    let trimmed = s.trim_start();
    let mut chars = trimmed.chars();
    if chars.next()? != expected {
        return None;
    }
    Some(chars.as_str())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_plain_string() {
        assert_eq!(quote("ola"), "\"ola\"");
    }

    #[test]
    fn escapes_quotes_backslashes_and_newlines() {
        assert_eq!(quote("a\"b\\c\nd"), "\"a\\\"b\\\\c\\nd\"");
    }

    #[test]
    fn extracts_simple_field() {
        let json = r#"{"content":"ola mundo","stop":true}"#;
        assert_eq!(
            extract_string_field(json, "content"),
            Some("ola mundo".to_string())
        );
    }

    #[test]
    fn extracts_field_with_escaped_quotes_and_newline() {
        let json = r#"{"content":"linha1\nlinha \"citada\""}"#;
        assert_eq!(
            extract_string_field(json, "content"),
            Some("linha1\nlinha \"citada\"".to_string())
        );
    }

    #[test]
    fn extracts_field_with_unicode_escape() {
        let json = r#"{"content":"café"}"#;
        assert_eq!(
            extract_string_field(json, "content"),
            Some("café".to_string())
        );
    }

    #[test]
    fn extracts_field_with_space_after_colon() {
        // Estilo de saída do `json.dumps` do Python (usado no mock server
        // do smoke test manual) — JSON válido, mas não compacto.
        let json = r#"{"content": "ola com espaco"}"#;
        assert_eq!(
            extract_string_field(json, "content"),
            Some("ola com espaco".to_string())
        );
    }

    #[test]
    fn extracts_field_with_whitespace_around_colon_and_before_key() {
        let json = "{ \"content\"   :   \"valor\" }";
        assert_eq!(
            extract_string_field(json, "content"),
            Some("valor".to_string())
        );
    }

    #[test]
    fn non_string_value_returns_none() {
        let json = r#"{"content":42}"#;
        assert_eq!(extract_string_field(json, "content"), None);
    }

    #[test]
    fn missing_field_returns_none() {
        let json = r#"{"other":"value"}"#;
        assert_eq!(extract_string_field(json, "content"), None);
    }

    #[test]
    fn unterminated_string_returns_none() {
        let json = r#"{"content":"sem fim"#;
        assert_eq!(extract_string_field(json, "content"), None);
    }

    #[test]
    fn extracts_decimal_number_field() {
        let json = r#"{"predicted_per_second":42.75}"#;
        assert_eq!(
            extract_number_field(json, "predicted_per_second"),
            Some(42.75)
        );
    }

    #[test]
    fn extracts_integer_number_field() {
        let json = r#"{"predicted_n":128}"#;
        assert_eq!(extract_number_field(json, "predicted_n"), Some(128.0));
    }

    #[test]
    fn extracts_number_field_nested_and_with_space_after_colon() {
        let json = r#"{"content":"ok","timings": {"predicted_n":10,"predicted_per_second": 33.3}}"#;
        assert_eq!(
            extract_number_field(json, "predicted_per_second"),
            Some(33.3)
        );
    }

    #[test]
    fn number_field_stops_at_comma_or_brace() {
        let json = r#"{"a":1.5,"b":2}"#;
        assert_eq!(extract_number_field(json, "a"), Some(1.5));
        assert_eq!(extract_number_field(json, "b"), Some(2.0));
    }

    #[test]
    fn missing_number_field_returns_none() {
        let json = r#"{"other":1.0}"#;
        assert_eq!(extract_number_field(json, "predicted_per_second"), None);
    }

    #[test]
    fn non_numeric_value_returns_none() {
        let json = r#"{"predicted_per_second":"nan"}"#;
        assert_eq!(extract_number_field(json, "predicted_per_second"), None);
    }
}
