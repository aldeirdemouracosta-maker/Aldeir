# Avaliação: modelo de IA generativa para a troca de rosto

Pesquisa de 21/10/2026. Objetivo: melhorar a qualidade da troca (hoje por malha, "colada") com um modelo de IA de **menos de 500 MB**,
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

## Conclusão
- Tecnicamente, o **MobileFaceSwap** é o único que cabe com folga e foi pensado para celular. O risco dele é **licença dos pesos** (a confirmar com os
  autores) e a conversão do formato original para ONNX/TFLite (não verificada).
- Os modelos mais populares (inswapper, HyperSwap) têm restrição de uso comercial. Para uso **pessoal**, o risco é menor; para **distribuir o app**, é preciso
  licença.
- GHOST não cabe em 500 MB sem quantização/poda (não avaliadas).

## Plano proposto (nada disso foi implementado)
1. Protótipo **no PC**, comparando o resultado da malha atual com um modelo candidato, em clipes seus (com consentimento).
2. Se compensar, converter para ONNX e medir no celular (CPU/XNNPACK/NNAPI).
3. Integrar como terceira variante opcional do APK, com o modelo **baixado pelo usuário** (não embutido no repositório), mantendo consentimento e selo
   "CONTEÚDO ALTERADO • IA".
