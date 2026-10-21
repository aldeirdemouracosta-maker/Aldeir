# Avaliação: modelo de IA generativa para a troca de rosto

Pesquisa de 21/10/2026. Objetivo: melhorar a qualidade da troca (hoje por malha, "colada") com um modelo de IA de **até 1 GB** (o limite inicial era 500 MB; o usuário aceitou até 1 GB),
rodando no aparelho, com licença que permita o uso. O que foi **verificado diretamente** está marcado com ✔; o resto vem de fontes secundárias.

| Opção | Tamanho | Licença do código | Licença dos pesos / pipeline | Cabe em 500 MB? |
|---|---|---|---|---|
| **Atual**: MediaPipe (pontos) + malha | 3,7 MB ✔ | Apache-2.0 (MediaPipe) | modelo de pontos do Google | sim, folgado |
| **inswapper_128** (InsightFace) | [~554 MB; fp16 ~277 MB](https://huggingface.co/martintomov/comfy/blob/c14576d0b7383229ef528030c4c536bce3930b71/insightface/inswapper_128_fp16.onnx) | MIT (código) | [pesos só para pesquisa não comercial; uso comercial exige licença do InsightFace](https://www.insightface.ai/solutions/face-swapping) | só a fp16 |
| **GHOST** (ai-forever) | gerador **737,5 MB** ✔, + ArcFace 261 MB ✔, + super-resolução 289 MB ✔ | Apache-2.0 ✔ | o pipeline usa modelos InsightFace (`glintr100` 261 MB ✔, `scrfd` 17 MB ✔), com a restrição acima | **não** |
| **MobileFaceSwap** (Baidu, AAAI 2022) | [0,50 M de parâmetros (≈ 2 MB em fp32), 0,33 GFLOPs por quadro](https://ar5iv.labs.arxiv.org/html/2201.03808) | Apache-2.0 ✔ | pesos só em Baidu/Google Drive; **licença dos pesos não declarada** no repositório ✔; treinado por destilação de SimSwap (CC-BY-NC) e FaceShifter | sim, de longe |
| HyperSwap (FaceFusion) | não verificado | não verificado | [listado como uso não comercial/pesquisa](https://huggingface.co/Pakaho-q1/Uni-Face) | — |

Notas:
- Pesos de modelo têm licença **separada** do código. "Código Apache/MIT" não significa que os pesos possam ser usados em qualquer app.
- GHOST e MobileFaceSwap também dependem de uma etapa de detecção/alinhamento e de um extrator de identidade (tipo ArcFace). Para o MobileFaceSwap
  não verifiquei qual e de que tamanho.
- Velocidade no celular: o artigo do MobileFaceSwap cita [19,7–25,6 FPS, mas sem dizer em que aparelho](https://ar5iv.labs.arxiv.org/html/2201.03808).
  Não há benchmark público que eu tenha achado de troca de rosto no ONNX Runtime Mobile; segundo a
  [documentação](https://onnxruntime.ai/docs/tutorials/mobile), o desempenho com XNNPACK/NNAPI depende do aparelho e do modelo e precisa ser medido.

## Peças alternativas ao InsightFace (verificadas no repositório `opencv/opencv_zoo`)

| Peça | Arquivo | Tamanho | Licença declarada |
|---|---|---|---|
| Detecção de rosto | YuNet `face_detection_yunet_2026may.onnx` ✔ | 0,23 MB (int8: 0,10 MB) | MIT ✔ |
| Reconhecimento de identidade | SFace `face_recognition_sface_2021dec.onnx` ✔ | 38,7 MB (int8: 9,9 MB) | Apache-2.0 ✔ |

Servem para **detectar e comparar rostos** com licença clara. Limites: (1) o SFace **não substitui** o ArcFace que o GHOST/inswapper esperam, porque o gerador é
treinado com o formato daquele vetor de identidade; (2) o repositório não informa os conjuntos de dados de treino, e dados de treino de reconhecimento
facial costumam ter termos próprios (não verificado). Para o app, o MediaPipe (já usado) cumpre a detecção; YuNet/SFace serviriam, por exemplo, para
conferir se a foto tem um rosto único e nítido.

## Com o limite de 1 GB
- **GHOST sem super-resolução**: gerador 737,5 MB ✔ + ArcFace 261,2 MB ✔ = ~999 MB, no limite (a detecção seria o MediaPipe, 3,7 MB). A super-resolução
  (289 MB) fica de fora. O ArcFace do GHOST vem de pesos no estilo InsightFace: a licença **precisa ser confirmada** antes de qualquer distribuição.
- **inswapper_128** (554 MB, ou 277 MB em fp16) passa a caber com folga, mas segue **só para pesquisa não comercial**.
- **MobileFaceSwap** continua o mais leve (~2 MB de rede), com a dúvida de licença dos pesos.
- Um modelo desse tamanho **não deve ir dentro do APK**: o certo é o usuário baixar depois, com consentimento, para o armazenamento do app.
- O gargalo no celular passa a ser **velocidade**, não tamanho: o gerador do GHOST tem cerca de 184 M de parâmetros (estimativa: 737,5 MB ÷ 4 bytes em fp32),
  e não medi o tempo por quadro. Espere bem mais lento que a malha atual (60 ms/quadro de composição no PC); pode levar muitos segundos por quadro.

## Conclusão
- Pelo critério de 500 MB, o **MobileFaceSwap** era o único que cabia com folga e foi pensado para celular. O risco dele é **licença dos pesos** (a confirmar com os
  autores) e a conversão do formato original para ONNX/TFLite (não verificada).
- Os modelos mais populares (inswapper, HyperSwap) têm restrição de uso comercial. Para uso **pessoal**, o risco é menor; para **distribuir o app**, é preciso
  licença.
- GHOST não cabe em 500 MB sem quantização/poda (não avaliadas).

## Plano proposto (nada disso foi implementado)
1. Protótipo **no PC**, comparando o resultado da malha atual com um modelo candidato, em clipes seus (com consentimento).
2. Se compensar, converter para ONNX e medir no celular (CPU/XNNPACK/NNAPI).
3. Integrar como terceira variante opcional do APK, com o modelo **baixado pelo usuário** (não embutido no repositório), mantendo consentimento e selo
   "CONTEÚDO ALTERADO • IA".
