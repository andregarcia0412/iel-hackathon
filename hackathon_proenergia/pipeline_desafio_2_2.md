# Pipeline proposta — desafio 2.2: carga por submercado, com e sem MMGD

## 1. Recomendação executiva

**Construir um previsor de correções sobre a semana anterior, com duas rotas: previsão direta da carga líquida e previsão de carga bruta menos MMGD.** Usar LightGBM, histórico recente, calendário e previsões meteorológicas históricas. Acrescentar uma combinação das duas rotas por horizonte e regime horário, somente se melhorar a validação.

A inovação está em adaptar a correção à mudança da curva solar, mantendo uma decomposição explicável e mensurável. O protótipo inicial cabe em seis regressores pequenos: três alvos × dois horizontes, compartilhando os quatro submercados.

**Prioridade:** construir uma avaliação temporal defensável antes de sofisticar os modelos. O PDF atribui 35% à evidência quantitativa e 25% ao impacto no negócio.

Este documento resulta da leitura de `desafio.md`, da seção 2.2 do PDF e da inspeção dos CSVs e arquivos compactados em `Datasets/`. Os números apresentados como diagnóstico foram calculados; melhorias dos modelos ainda são hipóteses a testar.

## 2. O que realmente temos nos dados

| Fonte local | Conteúdo e cobertura inspecionados | Uso recomendado |
|---|---|---|
| `carga_verificada.csv` | 2.155.824 registros, 33 códigos de área, de 01/01/2023 a 22/09/2026. Os quatro submercados têm 261.312 registros semi-horários, sem chaves duplicadas, nulos ou intervalos ausentes. | Fonte principal dos três alvos e dos históricos. |
| `DicionarioDados_Carga_Verificada.json` | Define carga global, líquida de MMGD, MMGD, consistência e intervalo encerrado em UTC. | Contrato semântico dos alvos. |
| `CURVA_CARGA_2023.csv` a `CURVA_CARGA_2026.csv` | 130.560 registros horários; quatro subsistemas; até 21/09/2026. | Conferência auxiliar; não concatenar com a carga líquida. |
| `dados_clima.7z` | Observado/reanálise e previsões D+1/D+7; temperatura, radiação, nebulosidade e umidade; agregações por submercado e dados de 27 cidades. | Meteorologia principal, respeitando os marcadores de proxy. |
| `novos.zip → calendario_submercado.csv` | 7.304 linhas, quatro submercados, 2023–2027; feriados, Carnaval, Corpus Christi, Quarta-feira de Cinzas, emendas e intensidade regional. | Calendário principal, após conferir a regra de construção. |
| `novos.zip → potencia_mmgd_solar_submercado_mensal.csv` | 224 linhas; quatro submercados × 56 meses; janeiro/2022 a agosto/2026. | Variável opcional de capacidade instalada; exige cuidado com disponibilidade e origem. |
| `novos.zip → carga_programada_dessem_2023_2026.csv` | 261.312 registros semi-horários; período geral de 2023 até 23/09/2026. Não traz emissão da previsão nem identificação de rodada. | Referência auxiliar condicionada à identificação do horizonte e do alvo. |
| `novos.zip → pld_horario_ccee_2023_2026.csv` | 130.848 registros horários; 01/01/2023 a 24/09/2026; sem duplicação de chave submercado/hora. | Valoração ilustrativa dos erros no teste. |
| `feriados.csv` | 112.258 registros, até 30/09/2026, por data/área/UF. | Auditoria do calendário agregado; exige agregação antes do join. |
| `INMET/2023.zip` a `2026.zip` | 567, 565, 594 e 639 arquivos de estação. As estações amostradas de 2026 terminam em agosto. | Validação meteorológica complementar; o MVP pode usar a base já agregada. |
| `empreendimento-geracao-distribuida.zip` | Um CSV com aproximadamente 1,43 GiB descompactado; UF, município, fonte e potência, entre outros campos. | Auditoria futura dos agregados; não precisa entrar no caminho crítico do MVP. |

### 2.1. Definição correta dos alvos

Usar os nomes reais do CSV:

```text
L = val_cargaglobalsmmgd   # carga líquida de MMGD
B = val_cargaglobal       # carga global incluindo MMGD
G = val_cargammgd         # parcela estimada atendida por MMGD

L ≈ B - G
```

A identidade foi conferida nas 261.312 linhas dos quatro submercados: o maior desvio absoluto foi aproximadamente **0,006 MW**, compatível com arredondamento. O JSON tem uma diferença de grafia: `val_cargaglobalsmmg`; o CSV usa `val_cargaglobalsmmgd`.

“Bruta” aqui significa a carga global segundo essa decomposição do ONS. Não equivale a afirmar medição direta de todo o consumo atrás do medidor. A própria MMGD é uma estimativa oficial.

O PDF informa que a série `CURVA_CARGA` incorpora MMGD desde abril/2023. Além disso, as curvas não coincidem exatamente com nenhuma das três colunas da carga verificada na comparação horária. Portanto, o pipeline deve manter **uma única fonte de verdade para os alvos**, sem misturar séries de metodologias diferentes.

### 2.2. Achados que mudam a implementação

1. **Os códigos agregados já existem:** filtrar `N`, `NE`, `S`, `SECO`. Somar todas as 33 áreas contaria agregados e componentes simultaneamente.
2. **O horário marca o fim da semi-hora:** `03:30 UTC` corresponde ao intervalo `00:00–00:30` de Brasília. A conversão precisa preceder a agregação.
3. **MMGD noturna não é zero:** nas horas de início de intervalo 00h–04h, as medianas foram aproximadamente 2,22 MW em N, 23,01 MW em NE, 46,27 MW em S e 119,18 MW em SECO. Preservar esse componente; não atribuir sua origem tecnológica sem documentação.
4. **Há anomalias mesmo sem nulos:** em N, em 08/02/2024, no intervalo iniciado às 10h, existe uma semi-hora com carga líquida de −1.463,73 MW. Identificar a anomalia antes da média horária, pois a média pode ocultá-la.
5. **Carga consistida é outro alvo:** `val_cargaglobalcons = val_cargaglobal + val_consistencia`, aproximadamente. Encontraram-se ajustes grandes, inclusive −28.460,684 MW em SECO em 28/03/2026 às 19h. Não substituir apenas a carga bruta pela consistida e conservar a líquida original.
6. **O histórico é revisado:** `din_atualizacao` dos quatro submercados está entre agosto e setembro/2026, inclusive para observações antigas. O backtest será retrospectivo sobre uma fotografia revisada, sem comprovação de todos os valores disponíveis em tempo real no passado.

### 2.3. Meteorologia: excelente atalho, com uma restrição fundamental

O CSV bruto do pacote climático tem **882.576 linhas, 27 cidades e 32.688 horários**, de 01/01/2023 a 23/09/2026, sem duplicação cidade/hora. As seis variáveis observadas não têm nulos.

A inspeção do bruto confirmou a documentação interna:

- Previsões completas D+1: a partir de **19/01/2024 às 09h**.
- Previsões completas D+7: a partir de **25/01/2024 às 09h**.
- D+7 tem **29 horas adicionais incompletas**, de 18/04/2026 às 10h a 19/04/2026 às 14h.
- Os agregados preenchem essas ausências com **clima observado**, marcado por `frac_pontos_proxy_observado > 0`.

**Regra principal: não usar esses proxies como previsão disponível.** Para o primeiro experimento, começar em fevereiro/2024 e excluir as linhas com proxy tanto do treino meteorológico quanto da avaliação principal. Comparar os modelos e o baseline exatamente nas mesmas linhas. Uma versão sem clima pode ser usada como fallback nas 29 horas, com desempenho e cobertura reportados à parte.

Os agregados usam pesos populacionais das capitais. Isso é uma aproximação razoável para começar com temperatura, mas a irradiância relevante para MMGD deveria refletir a distribuição das instalações, inclusive no interior. Repesar radiação é uma melhoria posterior.

**Detalhe técnico observado:** o ambiente tem PyArrow 19, e a leitura dos valores de um Parquet climático falhou com `Repetition level histogram size mismatch`; os arquivos foram gravados com PyArrow 25.0.1. A integridade do `.7z` foi verificada, e o CSV bruto foi lido integralmente. Reservar alguns minutos para um leitor compatível; se necessário, reconstruir os agregados a partir do CSV bruto e dos pesos documentados no README. Não confundir problema de leitura com ausência de dados.

## 3. Evidência inicial: onde existe oportunidade

Calculei a persistência semanal sobre a carga líquida horária, no período de desenvolvimento **01/01/2026–30/06/2026**, sem tratamento adicional de anomalias nem filtro climático:

| Submercado | MAPE geral | MAPE 08h–16h, inclusive | MAPE nas demais horas |
|---|---:|---:|---:|
| Norte | 3,51% | 4,61% | 2,85% |
| Nordeste | 4,96% | 7,52% | 3,43% |
| Sul | 9,93% | 15,78% | 6,42% |
| Sudeste/Centro-Oeste | 6,27% | 8,88% | 4,70% |

São 4.344 horas por submercado, sendo 1.629 na faixa 08h–16h. Essa faixa é uma **proxy fixa do núcleo solar**, não uma definição astronômica de todo o período diurno.

Isso dá fundamento para priorizar os erros diurnos, especialmente no Sul. Não demonstra, sozinho, que todo o erro é causado pela MMGD: temperatura, feriados e outros fatores também contribuem.

Esses números são um diagnóstico preliminar, não resultados de teste nem evidência de superioridade de um modelo. O baseline deverá ser recalculado na amostra exata do experimento final.

## 4. Contrato temporal: definir antes de gerar features

Cada previsão deve ser identificada por:

```text
origin_time, target_time, submercado, horizonte_dias
```

Para o MVP, adotar explicitamente uma **simulação de emissão no fechamento do dia D**, na fronteira de meia-noite que inicia D+1, supondo disponíveis os intervalos já encerrados de D:

- D+1: as 24 horas do dia seguinte a D.
- D+7: as 24 horas do sétimo dia depois de D.
- D+7 não significa uma sequência de sete previsões D+1 com observações intermediárias.
- Se depois for necessário prever todas as 168 horas, a expansão deve respeitar a mesma origem; não alimentar passos futuros com valores realizados.

Essa convenção viabiliza o baseline obrigatório `L(t−168h)` nos dois horizontes. Em um produto emitido antes do fechamento de D, parte desse baseline pode ainda não estar disponível em D+7. Nesse caso, adaptar os regressores e mostrar a diferença entre o benchmark acadêmico e a previsão executável naquele corte.

### 4.1. Disponibilidade das informações

Todo valor histórico usado como feature deve ter intervalo encerrado até a origem; quando existir carimbo de publicação, exigir também `available_at <= origin_time`.

O arquivo climático usa a API Previous Runs: `previous_day1` e `previous_day7` representam offsets de 24 e 168 horas em relação à validade meteorológica. Não são, por si só, uma única rodada emitida para as 24 horas do dia. Na convenção acima, as previsões selecionadas podem ser anteriores à origem, com atualização desigual ao longo da curva. Documentar essa aproximação e verificar os offsets; uma reprodução operacional exata exigiria rodada e horário de disponibilização, por exemplo via Single Runs.

O mesmo cuidado vale para carga revisada e capacidade instalada reconstruída. **Corte temporal de eventos não resolve sozinho revisões retroativas.** Apresentar essa limitação no card de resultados.

### 4.2. Exemplo do erro de vazamento mais provável

Para uma previsão D+7, `L(target_time−24h)` pertence a um dia ainda futuro na origem. É inválido, mesmo que tenha sido criado com `shift(24)` antes da separação treino/teste.

Já `L(target_time−168h)` e estatísticas dos intervalos encerrados nos últimos sete dias **até a origem** são válidos sob a convenção de fechamento adotada.

## 5. Pipeline de dados

```text
Carga verificada ── filtro dos 4 submercados ── auditoria ── agregação horária
                                                           │
Calendário agregado ────────────────────────────────────────┤
Previsões meteorológicas D+1 / D+7 ── exclusão de proxies ────┤
                                                           ▼
                              Tabela supervisionada por origem/alvo/horizonte
                                                           │
                          baseline + rota direta + rota decomposta
                                                           │
                               validação temporal → configuração congelada
                                                           │
                                    teste → card + gráficos + demonstração
```

### 5.1. Padronização da carga

1. Ler em blocos e filtrar `cod_areacarga in {N, NE, S, SECO}`.
2. Parsear `din_referenciautc` como UTC e converter para `America/Sao_Paulo`.
3. Subtrair 30 minutos para obter o início do intervalo.
4. Auditar valores fisicamente inválidos e a identidade `B−G≈L` antes de agregar.
5. Agrupar pelo início da hora e calcular a **média de duas semi-horas** para cada componente.
6. Exigir duas observações válidas por hora, mantendo uma flag de qualidade.
7. Reindexar na grade horária antes de qualquer `shift`: uma linha ausente não pode transformar “168 linhas” em algo diferente de “168 horas”.

As colunas estão em MW médios. Somar duas semi-horas dobraria incorretamente a carga. A energia de uma hora é `MWmed × 1h`, em MWh.

Adotar regra de qualidade antes do teste: marcar horas com componente de carga inválido, manter o registro da exclusão e avaliar todos os modelos na mesma máscara. Não excluir erros grandes simplesmente por piorarem o resultado. Ausências em lags podem receber fallback causal, como o valor de duas semanas antes, acompanhado de flag; não usar interpolação que enxergue o futuro.

Se o alvo oficial da banca for o consistido, definir conjuntamente `B*=val_cargaglobalcons` e `L*=B*−G`, reconferir o significado e refazer todos os benchmarks. Para a proposta atual, manter as colunas originais explicitamente identificadas.

### 5.2. Calendário

Preferir `calendario_submercado.csv`, que já contém uma linha por data/submercado. Conferir unicidade, dia da semana e algumas datas conhecidas antes do join.

Usar feriado nacional, intensidade regional, emenda, véspera, pós-feriado, Carnaval, Corpus Christi e Quarta-feira de Cinzas. Preservar a distinção entre feriado e ponto facultativo.

O arquivo original `feriados.csv` tem várias UFs por submercado/data. Um join direto multiplicaria a carga. A intensidade regional é preferível a marcar todo o submercado como feriado porque uma única UF tem uma data local.

### 5.3. Clima

- Temperatura prevista, radiação global prevista, nebulosidade e umidade: primeiras variáveis.
- A mesma rota de carga recebe o clima correspondente ao seu horizonte.
- Clima observado no horário-alvo não entra como preditor. Pode ser usado em análise de erro posterior.
- Radiação da Open-Meteo é média da hora anterior: para representar `[t,t+1h)`, alinhar a variável do timestamp original `t+1h`. Temperatura instantânea em `t` não deve ser deslocada automaticamente junto.
- Deslocar também o marcador de proxy e rastrear a validade original da previsão. Conferir que seu offset meteorológico permanece compatível com a origem.
- As flags de proxy são metadados de qualidade, não um mecanismo para tornar observação futura uma entrada válida.
- Os últimos dias do observado são análise/previsão operacional, conforme README; não tratá-los como reanálise consolidada.

### 5.4. Capacidade instalada

O MVP funciona usando o histórico recente de MMGD, sem depender da reconstrução cadastral. Se a capacidade mensal for incluída:

- Usar o último valor que poderia estar publicado na origem e mantê-lo constante em D+1/D+7.
- Um total de fechamento de mês não pode ser retropropagado ao início daquele mês.
- Sem data de publicação, uma defasagem de um mês é uma hipótese, não prova de disponibilidade histórica. Registrar a hipótese e fazer ablação sem essa variável.
- Verificar a origem de `mw_conectados_mes`: o cadastro bruto inspecionado contém atualização cadastral, que não deve ser confundida automaticamente com conexão.
- Agosto/2026 pode estar incompleto: em SECO, a tabela registra 5,772 MW adicionados, contra 159,119 MW em julho. Conferir antes de extrapolar tendência.

## 6. Features: poucas, com significado e disponibilidade verificável

| Grupo | Features iniciais |
|---|---|
| Identificação | Submercado categórico e hora-alvo; modelos separados por horizonte. |
| Calendário-alvo | Dia da semana, mês, seno/cosseno do dia do ano, fim de semana e flags de feriados/emendas. |
| Memória semanal | Lags 168, 336 e 672 horas de L, B e G; diferenças entre semanas. |
| Memória curta D+1 | Lags 24 e 48 horas, quando disponíveis na origem. |
| Estado na origem | Média de carga dos últimos 1 e 7 dias completos; diferença para os sete dias anteriores; perfil do último dia completo. |
| Clima previsto | Temperatura, radiação global, nebulosidade, umidade; temperatura ao quadrado ou graus de resfriamento como opção pequena. |
| Mudança solar | Quantil 95 da MMGD diurna nos 28 dias anteriores à origem; mudança entre janelas recentes; interação dessa escala com radiação prevista. |
| Qualidade | Flag de lag preenchido e idade da observação/fonte, quando disponível. |

Janelas de histórico são calculadas por submercado, encerradas na origem, nunca centradas no alvo. Pesos, escalas e parâmetros aprendidos são ajustados só com treino. Estatísticas causais recentes podem ser atualizadas a cada origem, inclusive durante o teste.

Para comparação justa, oferecer à rota direta os mesmos históricos e exógenas elegíveis da decomposta. A diferença principal deve ser **prever um alvo diretamente versus prever dois componentes**, e não conceder clima somente a uma delas.

## 7. Modelagem recomendada

### 7.1. Baseline obrigatório

\[
\widehat L_{base}(t)=L(t-168h)
\]

Implementar primeiro. O baseline tem o mesmo valor numérico para o mesmo alvo em D+1 e D+7 sob a convenção adotada; os modelos usam origens e meteorologia diferentes. Máscaras diferentes de avaliação podem produzir métricas diferentes.

### 7.2. Rota A — corrigir a previsão direta

Em vez de reaprender o nível inteiro, prever a diferença para a semana anterior:

\[
\widehat L_{dir}(t)=L(t-168h)+s_s f_{L,h}(X_{o,t,s})
\]

`s_s` é a mediana positiva da carga líquida do submercado no treino, congelada para inferência. O alvo do regressor é `(L(t)−L(t−168h))/s_s`.

Isso fornece uma referência forte e torna o modelo global menos dominado pela escala de SECO. As correções capturam mudanças de temperatura, calendário, nível recente e efeito solar.

### 7.3. Rota B — corrigir a carga bruta e prever a MMGD

Para a carga bruta:

\[
\widehat B(t)=B(t-168h)+s_s f_{B,h}(X_{o,t,s})
\]

Para a MMGD, começar com a mesma lógica:

\[
\widehat G(t)=\max\{0, G(t-168h)+a_{s,o}f_{G,h}(X_{o,t,s})\}
\]

`a_{s,o}` é uma escala causal: por exemplo, o quantil 95 da MMGD entre 08h e 16h nos 28 dias anteriores à origem, com fallback positivo estimado no treino. O alvo é `(G(t)−G(t−168h))/a_{s,o}`.

Essa normalização facilita aprender mudanças no perfil solar enquanto a geração distribuída cresce. `a × radiação_prevista / 1000` pode entrar como uma **proxy empírica**, não como fórmula exata de geração nem capacidade nominal.

Recompor:

\[
\widehat L_{dec}(t)=\widehat B(t)-\widehat G(t)
\]

Preservar a MMGD noturna aprendida. Não impor limite de capacidade fotovoltaica a toda a MMGD, pois a coluna pode incluir outras fontes. Se a recomposição gerar carga negativa, registrar a incoerência e aplicar uma regra de saída comum, predefinida; não esconder a frequência desse problema.

**Total: seis modelos**, um para cada combinação de `{L, B, G} × {D+1, D+7}`, com submercado categórico. Não precisamos treinar 24 modelos distintos por hora nem fazer previsão recursiva.

### 7.4. Configuração inicial

LightGBM com configuração pequena e única:

```text
objective = regression_l1
learning_rate = 0.05
num_leaves = 31
min_child_samples = 100
n_estimators = até 1500
reg_lambda = 1.0
random_state = 42
n_jobs = 4
early stopping = 100 iterações, com validação temporal explícita
```

A perda MAE é robusta para começar; a seleção final é pelo MAPE da **carga líquida reconstruída**, na escala original. Normalizar os alvos ajuda a equilibrar os submercados. Se houver tempo, testar uma única variante de pesos para aproximar MAPE, sem uma busca extensa de hiperparâmetros.

Usar os mesmos hiperparâmetros básicos nas duas rotas. Ganho de decomposição não é garantido: erros de B e G podem se somar ou se compensar.

### 7.5. Diferencial adicional: combinação por regime horário

\[
\widehat L_{final}=w_{h,r}\widehat L_{dec}+(1-w_{h,r})\widehat L_{dir}
\]

Escolher `w` em `{0; 0,25; 0,5; 0,75; 1}` apenas na validação, usando dois regimes fixos, `08h–16h` e demais horas, e os dois horizontes. São somente **quatro pesos globais**, evitando ajuste fino por dezenas de grupos.

O benefício potencial é aproveitar a decomposição onde ela funciona e a rota direta onde é mais estável. Manter na tabela de resultados as duas rotas individuais; a combinação não substitui a comparação exigida pelo desafio. Se não melhorar a validação de forma consistente, apresentar a melhor rota simples.

## 8. Validação temporal reproduzível

### 8.1. Divisão proposta

| Etapa | Datas dos alvos | Finalidade |
|---|---|---|
| Treino inicial | 01/02/2024–31/12/2025 | Período posterior à mudança de 2023 e com previsão meteorológica histórica. |
| Validação de treino | 08/01/2026–31/03/2026 | Early stopping e ajuste limitado. |
| Validação de decisão | 08/04/2026–30/06/2026 | Comparar rotas, ablações e escolher os quatro pesos. |
| Treino final | Até 30/06/2026 | Reajustar os modelos com configuração e número de iterações já definidos. |
| Teste final | 08/07/2026–22/09/2026 | Medir uma única vez após congelar as decisões. |

As folgas no início de janeiro, abril e julho ajudam a assegurar que as origens D+7 também sejam posteriores aos dados usados no ajuste ou na seleção da configuração anterior. Implementar a verificação por `origin_time`; não confiar apenas no nome do split. Histórico anterior ao início do treino pode fornecer lags, sem fornecer rótulos ao ajuste.

As 29 horas de proxy de abril são retiradas da avaliação meteorológica, incluindo qualquer linha adicional afetada pelo realinhamento da radiação. Todos os modelos comparados devem usar o mesmo conjunto de chaves elegíveis.

O teste será um **rolling-origin diário com parâmetros fixos**: em cada origem, atualizar apenas informações então disponíveis e emitir as curvas D+1/D+7. Uma observação do começo do teste pode virar histórico em uma origem posterior; isso é válido. Ela não pode ser incorporada a uma previsão já emitida.

Para o experimento principal, não é necessário retreinar diariamente. Evitar `train_test_split` aleatório e funções de early stopping que reservem amostras aleatórias internamente.

### 8.2. Métricas obrigatórias e diagnósticas

- **MAPE de carga líquida:** por submercado e horizonte; depois por faixa horária.
- **MAPE solar:** faixa 08h–16h predefinida, explicitamente chamada proxy do núcleo solar. Se houver tempo, acrescentar um recorte por geometria solar conhecida previamente.
- **MAPE macro:** média simples dos quatro MAPEs de submercado, separada por horizonte.
- **MAE em MW e viés médio:** complementam a leitura de negócio.
- **MAE da MMGD e da carga bruta:** explicam qual componente falhou. Evitar MAPE da MMGD em horas de valores próximos de zero.
- Cobertura: número de previsões, observações excluídas e acionamentos de fallback.
- Ganho relativo: `100 × (MAPE_baseline − MAPE_modelo) / MAPE_baseline`.

Para o MAPE, manter uma política explícita para alvos não positivos; não usar epsilon minúsculo para transformar dado inválido em percentual gigantesco. Todos os tratamentos devem ser iguais entre modelos.

O erro da recomposição satisfaz `e_L = e_B − e_G`. Um gráfico dos erros de B e G nas piores horas ajuda a explicar por que a decomposição ganhou ou perdeu.

### 8.3. Ablações com melhor retorno

Executar, nesta ordem:

1. Persistência semanal.
2. Rota direta com histórico e calendário.
3. Rota direta adicionando meteorologia prevista.
4. Rota decomposta com o mesmo conjunto de informação disponível.
5. Combinação das rotas, se aprovada na validação.

Isso permite afirmar quanto veio do aprendizado, do clima e da decomposição. Se o tempo apertar, preservar baseline e as duas rotas completas; a segunda ablação é a primeira a cortar.

## 9. Impacto no negócio e demonstração

### 9.1. Quantificação honesta

Para cada horizonte, calcular no teste:

\[
E_{erro}=\sum_t |L_t-\widehat L_t|\times 1h
\]

A redução em relação ao baseline é a redução do **volume absoluto de erro de previsão, em MWh**. Não representa energia fisicamente economizada.

Com o PLD do arquivo fornecido, uma análise adicional é:

\[
V_{proxy}=\sum_t |L_t-\widehat L_t|\times 1h\times PLD_t
\]

Nomear como **exposição teórica do erro valorada ao PLD**, não economia realizada. Liquidação efetiva depende de posição contratada, decisões, regras e sinal do desvio. O PLD realizado entra na avaliação ex post, não nas features D+7. Não somar D+1 e D+7 como se fossem dois volumes de energia distintos para o mesmo alvo.

### 9.2. DESSEM

A tabela disponível não permite identificar emissão, rodada e antecedência. Além disso, `val_cargaglobalprogramada` deve ser semanticamente alinhada ao alvo. Sem esclarecer esses pontos, não usá-la como preditor nem apresentar “superamos o DESSEM”. A comparação válida pode ser uma extensão após essa auditoria.

### 9.3. Entregáveis mínimos

1. Tabela de métricas: baseline, direta, decomposta e combinação; quatro submercados × dois horizontes.
2. Gráfico de uma semana: carga líquida real, baseline e previsões, com bruta/MMGD em painel separado.
3. Mapa de calor de ganho sobre baseline por hora e submercado.
4. Card de uma página: período, métrica, baseline, solução, delta, cobertura, impacto e “onde falha”.
5. Demonstração que escolhe origem histórica e submercado e reproduz as duas curvas futuras daquela origem.

O pitch pode dizer: **“Corrigimos a semana passada separando a demanda do efeito da geração distribuída. Medimos quando essa separação reduz o erro, especialmente nas horas solares.”** Acrescentar os números somente depois do teste.

## 10. Organização enxuta de implementação

```text
config.yaml              # datas, horizontes, fontes, seed e parâmetros
src/
  prepare.py             # leitura, horário, alvos e qualidade
  features.py            # contrato origem/alvo e features causais
  train.py               # baseline e seis regressores
  evaluate.py            # métricas, ablações e gráficos
run.py                   # execução de ponta a ponta
artifacts/
  models/
  predictions.parquet
  metrics.csv
  data_quality.json
  result_card.md
```

Stack: Python, pandas, NumPy, LightGBM, um leitor Parquet compatível e Matplotlib/Plotly. Uma página Streamlit é opcional após concluir a avaliação.

Salvar versões das dependências, configuração, lista de features, escala de cada submercado, hashes dos arquivos usados, períodos, seed e previsões com chaves completas. Isso já oferece rastreabilidade suficiente para o hackathon.

### Checagens indispensáveis

- Unicidade de `(submercado, timestamp)` e duas semi-horas válidas por hora.
- Identidade `B−G≈L`, com tolerância de 0,01 MW para os dados originais inspecionados.
- Cardinalidade dos joins preservada; calendário sem multiplicação por UF.
- Nenhuma feature histórica com fim de intervalo posterior à origem.
- Nenhum proxy observado disfarçado de previsão nas linhas avaliadas.
- Mesmo conjunto de chaves na comparação dos modelos.
- 24 saídas por submercado/horizonte/origem quando o dia for elegível completo.
- **Teste de causalidade útil:** alterar os dados posteriores a uma origem e verificar que as previsões já emitidas não mudam.

## 11. Plano de execução em aproximadamente quatro horas

| Tempo | Trabalho | Critério de conclusão |
|---|---|---|
| 0:00–0:40 | Resolver leitura climática, construir carga horária e auditar joins/alvos. | Tabela horária coerente e relatório de qualidade. |
| 0:40–1:15 | Criar origens, splits, lags e baseline. | Métricas reproduzíveis, sem acesso ao futuro. |
| 1:15–2:00 | Treinar rota direta e rota decomposta. | Seis modelos e previsões de validação. |
| 2:00–2:35 | Comparar, escolher pesos e congelar configuração. | Decisões baseadas só na validação. |
| 2:35–3:10 | Reajustar até junho e avaliar teste final. | Tabela final, cobertura e análise de falhas. |
| 3:10–4:00 | Gráficos, card, impacto e demonstração/pitch. | História sustentada por números reais. |

Se houver apenas duas horas, priorizar carga + calendário + clima já agregado, baseline, as duas rotas e um relatório estático. Uma comparação reproduzível vale mais que uma interface elaborada sem avaliação confiável.

## 12. Limitações e melhorias ordenadas por retorno

**Limitações a declarar:** histórico de carga revisado; MMGD estimada; meteorologia por capitais; ausência de rodadas/publicações em parte das fontes; extremos de clima e feriados raros; incompletude cadastral; extrapolação de crescimento da MMGD.

**Depois do MVP:**

1. Repesar a radiação pela distribuição espacial da MMGD e testar se realmente melhora.
2. Incorporar capacidade mensal após verificar origem e disponibilidade histórica.
3. Trocar o arquivo de offsets meteorológicos por rodadas rastreáveis a uma emissão comum.
4. Adicionar intervalos empíricos de erro calibrados temporalmente, deixando explícita a cobertura observada.
5. Investigar a comparação com DESSEM após alinhar alvo e antecedência.

**Decisão final:** começar com correção residual, decomposição supervisionada e meteorologia prevista. É uma solução pequena, explicável, adequada aos dados existentes e com uma hipótese de ganho concreta nas horas solares. O resultado do teste determinará qual rota merece ser usada.

## Referências utilizadas

- `Propostas de Desafio - Hackathon ProEnergia 2026.pdf`, seções 1.1 e 2.2.
- `desafio.md`.
- `Datasets/DicionarioDados_Carga_Verificada.json` e arquivos de dados locais descritos acima.
- `Datasets/dados_clima.7z → dados_clima/README.txt`, que documenta fontes, pesos e preenchimentos.
- [Open-Meteo — Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api): definição dos offsets e média retrospectiva da radiação.
- [Open-Meteo — Single Runs API](https://open-meteo.com/en/docs/single-runs-api): referência indicada pela documentação para rodadas com inicialização explícita.

Para submissão pública, completar o manifesto das tabelas auxiliares com URL de origem, data de extração e transformação. Os nomes dos CSVs, isoladamente, não demonstram a procedência das agregações.
