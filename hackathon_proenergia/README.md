# Previsão de carga do SIN — desafio 2.2

Pipeline executável para carga líquida, carga bruta e MMGD nos quatro submercados, com previsões horárias D+1/D+7, AutoML temporal, avaliação reproduzível e simulador de cenários.

## Abrir a demonstração

Depois de gerar os artefatos:

```bash
streamlit run app.py
```

Acesse `http://localhost:8501`. Selecione submercado, horizonte e dia do teste; altere temperatura, irradiância, nebulosidade, umidade ou feriado e clique em **Calcular cenário**. O aplicativo carrega o modelo persistido e recalcula as 24 previsões, sem retreinamento. Permite baixar o CSV completo e os parâmetros do cenário.

Os dados locais são históricos. A interface apresenta replay e sensibilidades hipotéticas, identificando a origem da previsão; a curva observada continua sendo referência do cenário original. As respostas a alterações não são efeitos causais comprovados.

Para outra pasta de artefatos:

```bash
SIN_ARTIFACTS=artifacts_nova_execucao streamlit run app.py
```

## Instalação

Python 3.11–3.13 e o executável `7z` no PATH. As versões executadas estão em `artifacts/manifest.json`.

```bash
python -m pip install -r requirements.txt
```

As dependências centrais já estavam instaladas no ambiente de desenvolvimento. O pacote climático foi reconstruído diretamente do CSV bruto, mantendo os pesos de população documentados, para evitar incompatibilidade dos Parquets originais com o leitor instalado.

## Executar a pipeline

Uma execução completa:

```bash
python run.py train
```

Preparação e treinamento separados:

```bash
python run.py prepare
python run.py train --reuse-prepared
```

O reuso verifica a configuração e os hashes dos dados originais. A execução não sobrescreve uma pasta que já contém `manifest.json`, para preservar um resultado final identificado. Para outro experimento:

```bash
python run.py train --output artifacts_nova_execucao
```

Testes:

```bash
python -m pytest tests -q
```

## Plano micro implementado

### 1. Integração e sanitização

- `carga_verificada.csv`: filtra `N`, `NE`, `S`, `SECO`.
- Converte fim de semi-hora UTC em início do intervalo de Brasília.
- Confere duplicações, finitude, positividade da carga e identidade `bruta − MMGD ≈ líquida`.
- Marca a semi-hora inválida antes de calcular a média horária. Uma hora requer duas semi-horas válidas.
- Preserva médias originais em `net_raw`, `gross_raw`, `mmgd_raw`; alvos inválidos ficam ausentes.
- Reindexa a grade horária para que 168 linhas representem 168 horas.
- Junta calendário agregado com validação de cardinalidade e consistência do dia da semana.
- Reconstrói previsões meteorológicas sem preencher ausências com observado.
- Realinha radiação, que no arquivo original representa a hora anterior.
- Junta PLD apenas depois da previsão, para avaliação econômica ex post.
- Salva capacidade instalada como tabela auxiliar. Ela não é feature enquanto publicação histórica e construção cadastral não forem verificadas.

Fontes essenciais: `Datasets/carga_verificada.csv`, `Datasets/dados_clima.7z`, `Datasets/novos.zip` e o dicionário da carga. Dados do INMET e cadastro completo da ANEEL ficam disponíveis para análises complementares.

### 2. Contrato temporal

Todas as previsões têm `origin_time`, `target_time`, `submercado`, `horizon` e antecedência até o fim do intervalo.

A origem é meia-noite de Brasília no fechamento de D, assumindo disponíveis os intervalos encerrados. D+1 é o dia que se inicia na origem; D+7 é o dia que começa seis dias depois dessa fronteira. As curvas são emitidas conjuntamente, sem atualização com observações intermediárias.

- Lags semanais: 168, 336 e 672 horas.
- Lags de 24 e 48 horas somente em D+1.
- Janelas recentes encerradas na origem; nenhuma janela centrada no alvo.
- Escala da MMGD: quantil 95 diurno dos últimos 28 dias disponíveis.
- Meteorologia prevista deve ter emissão/offset compatível com a origem.
- Observações posteriores à origem não alteram os inputs daquela previsão: isso é testado explicitamente.
- A lista de features é uma allowlist; alvos, valores realizados de PLD e metadados de revisão não entram no treinamento.

### 3. Splits

| Etapa | Datas dos alvos | Uso |
|---|---|---|
| Treino | 01/02/2024–31/12/2025 | Ajustar candidatos e transformações |
| Tuning | 08/01/2026–31/03/2026 | Escolher modelos da rota direta e da decomposição |
| Seleção | 08/04/2026–31/05/2026 | Escolher quatro pesos de combinação |
| Calibração | 08/06/2026–30/06/2026 | Quantis dos erros para faixas empíricas |
| Reajuste | 01/02/2024–30/06/2026 | Reajustar somente os vencedores, com decisões congeladas |
| Teste | 08/07/2026–22/09/2026 | Medir desempenho final |

Os intervalos entre etapas respeitam também a origem D+7. Os parâmetros ficam fixos no teste; o histórico causal é atualizado em cada origem. Exclusões ficam em `prepared/excluded_rows.csv`.

### 4. AutoML temporal

Implementado com scikit-learn: uma busca automatizada, limitada e reproduzível, com cinco configurações de quatro famílias:

1. Ridge com imputação e padronização ajustadas só no treino.
2. Extra Trees.
3. Random Forest.
4. HistGradientBoosting com perda absoluta.
5. HistGradientBoosting com perda quadrática e outra complexidade.

São **30 ajustes de candidatos**: cinco configurações × três alvos × dois horizontes. O baseline semanal é calculado independentemente. Os modelos aprendem resíduos em relação à semana anterior, normalizados por escala de submercado ou escala causal da MMGD.

Por horizonte:

- A rota direta é selecionada pelo MAPE macro da carga líquida na janela de tuning.
- As 25 combinações carga bruta/MMGD são comparadas pelo MAPE da carga líquida recomposta, não apenas pelos erros individuais dos componentes.
- Na janela seguinte, quatro pesos globais são escolhidos na grade `[0, .25, .5, .75, 1]`: horizonte × núcleo solar/demais horas.
- O treinamento usa contagens de iteração fixas por candidato; o early stopping interno aleatório do HistGradientBoosting está desabilitado.
- Nenhuma seleção usa o teste.

Essa busca substitui a dependência inicialmente proposta em LightGBM por algoritmos já disponíveis. Não utiliza validação cruzada aleatória nem um framework genérico de AutoML com pressupostos IID.

### 5. Intervalos e avaliação

Faixas empíricas de 90% usam quantis de erros absolutos por horizonte, submercado e regime horário, em junho. A calibração é anterior ao reajuste final; portanto, as faixas não têm garantia formal de cobertura após o reajuste. A cobertura efetivamente observada no teste é reportada.

Métricas: MAPE por submercado, horizonte, faixa solar e cada hora; MAE, RMSE, viés, P95 do erro, volume absoluto de erro em MWh e exposição teórica ao PLD. MAPE macro é a média dos quatro submercados. A faixa solar fixa é 08h–16h, inclusive, uma aproximação do núcleo solar.

A redução de exposição ao PLD não equivale a lucro, e a redução de erro em MWh não equivale a energia fisicamente economizada. Os horizontes são avaliados separadamente.

## Artefatos produzidos

```text
artifacts/
  run_config.json
  manifest.json                      # fontes/hashes, código, versões e decisões
  prepared/
    hourly.parquet                   # carga horária sanitizada + valores originais
    weather.parquet                  # somente previsões; ausências explícitas
    calendar.parquet
    pld.parquet
    capacity_auxiliary.parquet
    features_d1.parquet              # todos os inputs, rótulos, flags e splits
    features_d7.parquet
    data_quality.json
    load_anomalies.csv
    excluded_rows.csv
    split_coverage.csv
  search/
    trials.csv                       # parâmetros, duração e erros de cada candidato
    d*_*.joblib                      # todos os candidatos ajustados no treino inicial
    tuning_predictions_d*.parquet
    decomposition_combinations.csv
    selected_models.json
    blend_search.csv
    selection_predictions.parquet
    calibration_predictions.parquet
    frozen_decisions.json
  models/
    forecast_bundle.joblib           # seis vencedores, escalas, pesos e intervalos
  reports/
    test_predictions.parquet         # auditoria completa por previsão
    test_predictions.csv.gz
    metrics.csv
    macro_metrics.csv
    component_metrics.csv
    daily_metrics.csv
    worst_100_predictions.csv
    result_card.md
    week_d1.html / week_d7.html
    hourly_gain_d1.html / hourly_gain_d7.html
```

O registro de teste inclui todas as features, origem, hora-alvo, valores reais e originais, baseline, carga bruta/MMGD previstas, rotas, pesos, previsão final, limites, erros assinados/absolutos/percentuais, cobertura, PLD, identificação do modelo e execução. Erros assinados usam `previsto − real`.

## Inferência com dados atualizados

Além do simulador, `sin_forecast.inference.predict_request` oferece o mesmo caminho de features e modelo para dados externos. A inferência é local e não treina novamente. Atualização das fontes é responsabilidade do chamador; o programa não apresenta as bases históricas como meteorologia ao vivo.

Crie `request.json`:

```json
{
  "origin_time": "2026-09-24T00:00:00-03:00",
  "horizon": 1,
  "submercado": "NE",
  "history_path": "dados_atualizados/historico_horario.csv",
  "weather_path": "dados_atualizados/previsao_meteorologica.csv",
  "overrides": {"temperature_delta": 2.0, "radiation_multiplier": 0.8}
}
```

```bash
python run.py predict --request request.json --predictions artifacts/previsao_atual.csv
```

Contrato de `historico_horario.csv`:

```text
submercado,target_time,net,gross,mmgd
```

Hora = início do intervalo; potência em MW médios; pelo menos 28 dias de histórico, preferencialmente 56; timezone explícito. Somente intervalos encerrados até a origem são utilizados. Valores inválidos são marcados. A função verifica se o histórico é recente o suficiente.

Contrato de `previsao_meteorologica.csv`:

```text
target_time,issued_at,temperature,radiation,cloud,humidity
```

Cobrir as 24 horas-alvo. `issued_at` deve ser anterior ou igual à origem, com timezone explícito. Temperatura em °C, radiação em W/m² **média do próprio intervalo-alvo**, nebulosidade e umidade em %. Não usar clima observado futuro. As previsões da semana anterior podem vir do cache histórico, quando disponíveis; ausências nesse contexto adicional passam pelo imputador ajustado no treino.

`history_path` é opcional para replay com o histórico local. `calendar_path` permite fornecer um calendário novo no contrato da tabela preparada, com `date` incluindo fuso e as mesmas colunas de calendário. O calendário local chega a dezembro/2027.

API Python:

```python
from pathlib import Path
from sin_forecast.inference import predict_request

predictions = predict_request(request, Path("artifacts"))
```

## Limitações técnicas registradas

- A carga é uma fotografia revisada em 2026, sem todas as versões históricas disponíveis em cada origem.
- Emissão na fronteira diária pressupõe disponibilidade imediata dos intervalos encerrados.
- Previous Runs fornece offsets de 24/168h; não comprova uma única rodada meteorológica publicada para toda a curva.
- MMGD é estimada; a agregação climática usa capitais e pesos populacionais.
- O arquivo de DESSEM não identifica emissão/rodada; não há afirmação de superioridade frente a ele.
- A carga original e a consistida não são misturadas silenciosamente.
- A calibração empírica dos intervalos pode perder cobertura sob mudanças de regime ou cenários extremos.

O planejamento macro e a inspeção das fontes estão em [pipeline_desafio_2_2.md](pipeline_desafio_2_2.md).
