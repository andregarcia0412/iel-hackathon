<div align="center">

# ⚡ SinVision

**Previsão horária de carga do SIN por submercado, com e sem MMGD**

Dashboard interativo e assistente com IA para comparar a previsão **direta** da carga líquida com a abordagem **decomposta** (carga bruta − geração distribuída) nos quatro submercados do Sistema Interligado Nacional.

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.64+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![Ollama](https://img.shields.io/badge/Ollama-LLM-000000?logo=ollama&logoColor=white)](https://ollama.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-AutoML%20temporal-F7931E?logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![pandas](https://img.shields.io/badge/pandas-150458?logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Hackathon](https://img.shields.io/badge/Hackathon-ProEnergia%202026-044947)](hackathon_proenergia/desafio.md)

</div>

---

## 📌 Sobre o projeto

O ONS enxerga a **carga líquida** da rede: o consumo total menos o que a micro e minigeração distribuída (MMGD, majoritariamente solar) injeta localmente. Com a expansão da MMGD, a curva observada passou a "afundar" no horário de sol, e prever carga hoje significa prever duas coisas ao mesmo tempo: o **consumo** e a **geração distribuída**.

O SinVision responde ao **Desafio 2 do Hackathon ProEnergia 2026**: prever a carga horária de cada submercado (**SE/CO, S, NE e N**) para **D+1** e **D+7**, comparando duas rotas:

| Abordagem | Como funciona |
|---|---|
| **Direta** | Prevê a carga líquida diretamente |
| **Decomposta** | Prevê a carga bruta e a MMGD separadamente e recompõe `líquida = bruta − MMGD` |
| **Final** | Combinação das duas, com pesos por horizonte e faixa horária (núcleo solar × demais horas) |

O resultado é traduzido em impacto de negócio: **erro evitado em MWh** e **economia estimada em R$** com base no PLD de cada hora.

## ✨ Funcionalidades

- 🔐 **Tela de login** com identidade visual própria
- 📊 **Cards de métricas**: energia economizada, economia estimada e MAPE das abordagens direta e decomposta
- 📈 **Gráfico de previsão** das cargas líquida e bruta ao longo do dia
- 🌤️ **Dados do período**: irradiância prevista, potência de MMGD instalada, temperatura e calendário (feriados/emendas)
- 🗺️ **Heatmap de MAPE** por submercado e faixa horária (madrugada, manhã, sol, rampa e noite)
- 🎛️ **Filtros** por submercado e horizonte (próximo dia / próximos 7 dias)
- 🤖 **Assistente com IA** (via Ollama) que lê o estado atual do dashboard e explica gráficos, métricas e abordagens, respondendo em streaming

## 🧠 Modelo de previsão

A pipeline de modelagem fica em [`hackathon_proenergia/`](hackathon_proenergia/README.md) e inclui:

- Sanitização e agregação horária da carga verificada, clima previsto, calendário e PLD
- Contrato temporal rígido, sem vazamento de dados futuros (lags semanais, janelas causais)
- **AutoML temporal** com scikit-learn: Ridge, Extra Trees, Random Forest e HistGradientBoosting, aprendendo resíduos sobre a semana anterior
- Splits temporais separados para treino, tuning, seleção, calibração e teste
- Faixas empíricas de 90% e métricas como MAPE, MAE, RMSE, viés e exposição ao PLD

O dashboard consome as previsões do último mês de teste já exportadas em [`data/`](data/).

## 🗂️ Estrutura

```text
.
├── src/iel_hackathon/        # App Streamlit (SinVision)
│   ├── main.py               # Entrada: login + dashboard
│   ├── forecast.py           # Leitura e agregação das previsões
│   ├── chat/                 # Assistente com IA (Ollama)
│   ├── components/           # Cards, gráfico, filtros, heatmap
│   ├── login/  sidebar/      # Telas e navegação
│   └── static/               # Fontes, ícones e imagens
├── data/                     # Previsões, componentes e capacidade de MMGD
├── hackathon_proenergia/     # Pipeline de previsão (sin_forecast) e documentação do desafio
├── scripts/                  # Extração dos dados usados pelo dashboard
└── tests/                    # Testes do app
```

## 🚀 Como rodar

**Pré-requisitos:** Python 3.13 e [uv](https://docs.astral.sh/uv/).

```bash
# 1. Clone o repositório
git clone git@github.com:andregarcia0412/iel-hackathon.git
cd iel-hackathon

# 2. Instale as dependências
uv sync

# 3. Configure o assistente (opcional)
cp .env.example .env
# edite .env e preencha OLLAMA_API_KEY

# 4. Suba o app
uv run streamlit run src/iel_hackathon/main.py
```

Acesse `http://localhost:8501`.

### Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `OLLAMA_API_KEY` | — | Chave da API do Ollama. Sem ela, o dashboard funciona e o chat fica desabilitado |
| `OLLAMA_MODEL` | `gemma4:31b-cloud` | Modelo usado pelo assistente |
| `OLLAMA_HOST` | `https://ollama.com` | Endpoint do Ollama |

No **Streamlit Community Cloud**, use `.streamlit/secrets.toml` (veja [`secrets.toml.example`](.streamlit/secrets.toml.example)); os secrets têm prioridade sobre as variáveis de ambiente.

## 🧪 Testes

```bash
uv run pytest
```

Para a pipeline de previsão, veja as instruções em [`hackathon_proenergia/README.md`](hackathon_proenergia/README.md).

## 📄 Documentação do desafio

- [Resumo do desafio](hackathon_proenergia/desafio.md)
- [Proposta da pipeline](hackathon_proenergia/pipeline_desafio_2_2.md)
- [Edital com as propostas de desafio (PDF)](hackathon_proenergia/Propostas%20de%20Desafio%20-%20Hackathon%20ProEnergia%202026.pdf)

---

<div align="center">

Feito para o **Hackathon ProEnergia 2026** ⚡

</div>
