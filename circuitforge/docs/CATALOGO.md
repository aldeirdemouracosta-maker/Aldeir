# Catálogo de circuitos

_Gerado por `tools/gen_catalog.py`._
**57 circuitos.**


## 🔌 Fundamentos (12)

| Circuito | Descrição | Análises |
|---|---|---|
| `rc_lowpass` **Filtro RC passa-baixa** | Atenua frequências acima da frequência de corte fc = 1/(2πRC). | Transient, AC (Bode) |
| `rc_highpass` **Filtro RC passa-alta** | Bloqueia o nível DC e frequências baixas; fc = 1/(2πRC). | Transient, AC (Bode) |
| `rc_integrator` **Integrador RC (onda quadrada → triangular)** | Com τ ≫ T o capacitor integra a entrada: quadrada vira triangular. | Transient |
| `rc_differentiator` **Diferenciador RC (quadrada → pulsos)** | Com τ ≪ T a saída é a derivada da entrada: picos nas bordas. | Transient |
| `voltage_divider` **Divisor de tensão** | Vout = Vin·R2/(R1+R2). | Ponto de operação, Varredura DC |
| `series_rlc` **Circuito RLC série (ressonância)** | Ressonância em f0 = 1/(2π√LC); a tensão no capacitor sobe por Q. | AC (Bode), Transient |
| `halfwave_rectifier` **Retificador de meia-onda** | Um diodo conduz só os semiciclos positivos. | Transient |
| `fullwave_bridge` **Retificador de onda completa (ponte)** | Quatro diodos aproveitam os dois semiciclos. | Transient |
| `inverting_opamp` **Amplificador inversor (amp-op)** | Ganho fechado = −Rf/Rin. | Transient, AC (Bode) |
| `noninverting_opamp` **Amplificador não-inversor (amp-op)** | Ganho = 1 + R2/R1, alta impedância de entrada. | Transient, AC (Bode) |
| `common_emitter` **Amplificador emissor-comum (BJT)** | Polarização por divisor de tensão, capacitor de bypass no emissor. | Transient, AC (Bode), Ponto de operação |
| `astable_555` **Oscilador astável 555** | Multivibrador com modelo comportamental do CI 555 (comparadores + flip-flop). | Transient |

## 🔋 Fontes de alimentação (7)

| Circuito | Descrição | Análises |
|---|---|---|
| `zener_regulator` **Regulador shunt com diodo Zener** | O Zener mantém a tensão quase constante enquanto houver corrente reversa suficiente. | Regulação de linha (DC), Ponto de operação |
| `series_regulator` **Regulador série (Zener + transistor)** | Seguidor de emissor com referência Zener: o transistor amplifica a corrente da carga. | Regulação de linha (DC), Ponto de operação |
| `ldo_adjustable` **Regulador linear ajustável com amp-op (LDO com PMOS)** | Amp-op compara a saída (divisor) com a referência de 1,25 V e comanda o PMOS de passagem. | Degrau de carga |
| `buck_converter` **Conversor buck (abaixador chaveado)** | Chave + diodo + LC: Vout = D·Vin com rendimento alto. | Transient |
| `boost_converter` **Conversor boost (elevador chaveado)** | Eleva a tensão: Vout = Vin/(1−D). | Transient |
| `rectifier_filter` **Retificador com filtro capacitivo** | Ponte + capacitor: DC com ondulação (ripple) ΔV ≈ I/(2fC). | Transient |
| `linear_psu` **Fonte linear completa (trafo + ponte + filtro + regulador)** | Rede → transformador → ponte → capacitor → regulador série. A fonte clássica de bancada. | Transient |

## 💻 Placas de computador (6)

| Circuito | Descrição | Análises |
|---|---|---|
| `cpu_vrm` **VRM de CPU – buck de 2 fases entrelaçadas (12 V → 1,1 V)** | Duas fases defasadas de 180° dividem a corrente e reduzem a ondulação; degrau de carga de 4 A para 24 A. | Degrau de carga |
| `usb_3v3_ldo` **USB 5 V → 3,3 V (LDO de placa)** | Regulador linear que alimenta microcontroladores e periféricos a partir da porta USB. | Degrau de carga |
| `pdn_impedance` **Impedância da rede de alimentação (PDN) com desacoplamento** | Curva |Z| vista pelo chip: VRM, capacitores de bulk, MLCCs e capacitância do die. | Impedância (AC) |
| `i2c_bus` **Barramento I²C – resistor de pull-up e capacitância** | Borda de subida RC limita a velocidade: tr(30–70 %) ≈ 0,847·Rp·Cb. | Transient |
| `power_on_reset` **Reset na energização (RC + Schmitt)** | Mantém o processador em reset por RC·ln(...) após a tensão estabilizar. | Transient |
| `ring_oscillator` **Oscilador em anel CMOS (clock de CI)** | Número ímpar de inversores em anel: oscila com f ≈ 1/(2·N·td). | Transient |

## 🧠 Placas e circuitos de IA (4)

| Circuito | Descrição | Análises |
|---|---|---|
| `analog_neuron` **Neurônio analógico (soma ponderada + tanh)** | Amp-op somador (pesos = Rf/Ri) seguido de par diferencial BJT, que realiza a ativação ≈ tanh. | Curva de ativação (x1 de −2 a 2 V) |
| `crossbar_mvm` **Crossbar resistivo – multiplicação matriz-vetor analógica** | Matriz 3×2 de condutâncias + conversores corrente-tensão: Iⱼ = Σ Gᵢⱼ·Vᵢ pela lei de Ohm e Kirchhoff. | Ponto de operação |
| `sensor_frontend` **Front-end de sensor para IA de borda (pré-amp + anti-aliasing)** | Microfone → amplificador → filtro Sallen-Key passa-baixa de 2ª ordem antes do ADC de um TinyML. | AC (Bode), Transient |
| `accelerator_vrm` **VRM de acelerador de IA/GPU (degrau de 20 A a 120 A)** | Fonte de núcleo de acelerador: 4 fases entrelaçadas alimentando carga que muda quase instantaneamente. | Degrau de carga |

## 🔊 Amplificadores de som (4)

| Circuito | Descrição | Análises |
|---|---|---|
| `audio_preamp` **Pré-amplificador de áudio (amp-op, acoplamento AC)** | Estágio não-inversor com capacitores de acoplamento e polarização central. | AC (Bode), Transient |
| `class_ab_amp` **Amplificador de potência classe AB (amp-op + par complementar)** | Par NPN/PNP polarizado por diodos dentro da malha de realimentação do amp-op. | Transient, AC (Bode) |
| `class_d_amp` **Amplificador classe D (PWM + filtro LC)** | Comparador gera PWM, meia-ponte chaveia e o filtro LC recupera o áudio com alta eficiência. | Transient |
| `crossover_2way` **Divisor de frequências (crossover) de 2 vias** | Filtro passivo de 2ª ordem (Butterworth) divide graves para o woofer e agudos para o tweeter. | AC (Bode) |

## 🎸 Pedais de guitarra (5)

| Circuito | Descrição | Análises |
|---|---|---|
| `clean_boost` **Pedal Clean Boost (1 transistor)** | Emissor-comum com ganho ajustável por degeneração parcial do emissor, alimentado por bateria de 9 V. | Transient, AC (Bode) |
| `overdrive_ts` **Overdrive estilo Tube Screamer (amp-op + diodos)** | Amp-op com diodos em antiparalelo na realimentação: compressão suave e 'saturação de válvula'. | Transient, AC (Bode, sinal pequeno) |
| `fuzz_face` **Fuzz Face (2 transistores com realimentação)** | Dois transistores com realimentação CC criam um som saturado e 'rasgado'. | Transient |
| `wah_pedal` **Pedal Wah-Wah (filtro ressonante LC)** | Filtro passa-faixa LC cuja frequência de pico varia com a posição do pedal (400 Hz a 2,2 kHz). | AC (Bode) |
| `tremolo` **Tremolo (LFO + amplificador controlado por tensão)** | Um oscilador de baixa frequência modula o ganho do sinal da guitarra. | Transient |

## ☀️ Energia solar (3)

| Circuito | Descrição | Análises |
|---|---|---|
| `pv_panel_iv` **Painel fotovoltaico – curva I-V e P-V** | Modelo de um diodo de painel de 36 células (≈ 130 W). Varre a tensão e mostra corrente e potência. | Curva I-V |
| `solar_buck_charger` **Carregador solar de bateria (buck, MPPT manual)** | Painel → capacitor → conversor buck → bateria de 12 V. Varie o ciclo de trabalho para achar o ponto de máxima potência. | Transient |
| `solar_shading` **Sombreamento parcial com diodos de bypass** | Dois sub-conjuntos de 18 células em série; um recebe sombra. O diodo de bypass evita perda total e queima (hot-spot). | Curva I-V |

## 🚗 Circuitos veiculares (6)

| Circuito | Descrição | Análises |
|---|---|---|
| `car_usb_charger` **Carregador USB veicular (12–14,4 V → 5 V / 2,4 A)** | Buck de bateria automotiva para USB, com diodo Schottky. | Transient |
| `load_dump_clamp` **Proteção contra load dump (TVS) na rede 12 V** | Quando a bateria é desligada com o alternador carregando, surge um pico de dezenas de volts que destrói eletrônicas sem proteção. | Transient |
| `alternator_rectifier` **Alternador trifásico com ponte retificadora** | Três enrolamentos em Y, seis diodos, bateria e carga: a geração de energia do carro. | Transient |
| `relay_flyback` **Acionamento de relé com diodo de roda livre** | Ao desligar uma bobina, o indutor gera pico de tensão; o diodo flyback o elimina. | Transient |
| `led_pwm_dimmer` **Dimmer PWM para LED (farol/DRL)** | MOSFET chaveia um conjunto de LEDs a 500 Hz; a razão cíclica ajusta a luminosidade. | Transient |
| `reverse_polarity` **Proteção contra inversão de polaridade (PMOS vs diodo)** | Um MOSFET canal P em série perde bem menos que um diodo e protege contra bateria invertida. | Transient |

## 📻 Rádio, TV e som (5)

| Circuito | Descrição | Análises |
|---|---|---|
| `am_detector` **Receptor AM – detector de envoltória** | Diodo + RC recupera o áudio de uma portadora modulada em amplitude. | Transient |
| `lc_tuner` **Sintonia de rádio (circuito LC paralelo)** | Capacitor variável desloca a ressonância e seleciona a estação: f0 = 1/(2π√LC). | AC (Bode) |
| `superhet_mixer` **Misturador do receptor super-heteródino (RF × LO → FI)** | Multiplicador gera soma e diferença de frequências; o tanque LC seleciona a FI de 455 kHz. | Transient |
| `tv_sync_separator` **Separador de sincronismo de TV (vídeo composto)** | Extrai os pulsos de sincronismo horizontal (15,73 kHz) do sinal de vídeo composto. | Transient |
| `colpitts_oscillator` **Oscilador Colpitts (oscilador local de rádio)** | Transistor + tanque LC com divisor capacitivo: gera a portadora de RF. | Transient |

## 📡 Antenas e RF (5)

| Circuito | Descrição | Análises |
|---|---|---|
| `dipole_equivalent` **Dipolo de meia-onda – circuito equivalente RLC** | A antena vista como impedância: 73 Ω de radiação em série com reatâncias que se anulam em f0. | Casamento (AC) |
| `quarter_wave_transformer` **Transformador de impedância λ/4 (linha de transmissão)** | Um segmento de linha com λ/4 e Z = √(Zs·ZL) casa uma carga à linha. | Casamento (AC) |
| `l_match` **Rede de casamento em L (50 Ω → carga menor)** | Capacitor em paralelo + indutor em série transformam a impedância de uma antena curta para 50 Ω. | Casamento (AC) |
| `antenna_bandpass` **Filtro passa-faixa de antena (Butterworth de 3ª ordem)** | Seleciona a faixa de FM (88–108 MHz) e rejeita sinais fora dela. | AC (Bode) |
| `tv_balun_4to1` **Balun 4:1 de antena de TV (300 Ω → 75 Ω)** | Transformador de banda larga casa a fita paralela de 300 Ω ao cabo coaxial de 75 Ω. | Casamento (AC) |
