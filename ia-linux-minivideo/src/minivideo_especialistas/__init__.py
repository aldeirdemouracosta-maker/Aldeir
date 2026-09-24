"""Especialistas locais de planejamento e edição de vídeo.

Papéis (JSON validado por ``schemas/*.schema.json``):
- Diretor: pedido → cenas e critérios de aceitação;
- Editor: cenas → operações e motores cadastrados;
- Fiscal de hardware: aprova, reduz ou suspende conforme sensores e limites;
- Continuísta: fronteiras, áudio e coerência entre trechos.
Nenhum papel executa comandos: só ``pipeline.compilar`` e o executor
transformam JSON validado em argumentos de ferramentas cadastradas.
"""

__version__ = "0.4.0"
