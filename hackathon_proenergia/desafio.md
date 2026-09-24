Claro. O desafio da imagem é o **“Desafio 2 | Previsão de carga do SIN por submercado — com e sem MMGD”**.

A ideia central é desenvolver um modelo de **previsão de séries temporais para estimar a carga elétrica horária de cada submercado do Sistema Interligado Nacional (SIN)**, levando em consideração que a expansão da geração solar distribuída passou a alterar a forma como a demanda é observada pelo sistema.

### Qual é o problema?

O ONS observa aquilo que podemos chamar de **carga líquida** da rede. De forma simplificada:

$$
\text{Carga líquida} =
\text{Consumo total} -
\text{Geração distribuída}
$$

Uma parcela importante dessa geração distribuída é a **MMGD — Micro e Minigeração Distribuída**, principalmente geração solar fotovoltaica instalada em residências, empresas, indústrias etc.

Imagine que uma região esteja consumindo **10 GW**, mas painéis solares locais estejam produzindo **3 GW**. Para o ONS, a carga observada na rede pode aparecer aproximadamente como:

$$
10 - 3 = 7\text{ GW}
$$

O problema é que a geração solar depende fortemente de **hora do dia, radiação solar, nebulosidade, chuva, estação do ano e localização**. Consequentemente, a série histórica de carga observada pelo ONS foi sendo modificada conforme a MMGD cresceu.

Por isso, a imagem resume o problema dizendo que:

> “Prever carga hoje é prever duas coisas ao mesmo tempo.”

Ou seja, você precisa entender tanto o **comportamento do consumo de energia** quanto o **efeito da geração distribuída sobre a carga observada**.

### O que deve ser previsto?

A equipe deve produzir **previsões horárias de carga por submercado** para dois horizontes:

$$
D+1
$$

previsão para o **dia seguinte**, e

$$
D+7
$$

previsão para **sete dias à frente**.

Provavelmente vocês trabalharão separadamente com os submercados do SIN, como:

* Sudeste/Centro-Oeste;
* Sul;
* Nordeste;
* Norte.

O resultado, portanto, seria algo semelhante a:

| Data/hora   | Submercado | Carga prevista |
| ----------- | ---------- | -------------: |
| 24/09 08:00 | Nordeste   |      12.500 MW |
| 24/09 09:00 | Nordeste   |      12.800 MW |
| ...         | ...        |            ... |
| 30/09 23:00 | Nordeste   |      13.100 MW |

### As duas abordagens que o hackathon quer comparar

Esse é provavelmente o ponto mais importante da proposta.

A primeira abordagem é prever **diretamente a carga líquida**:

$$
\boxed{
\hat L_{\text{líquida}}(t)
=
f(X_t)
}
$$

O modelo aprende diretamente a série histórica observada pelo ONS.

A segunda abordagem é tentar decompor o problema:

$$
\boxed{
\text{Carga líquida}
=
\text{Carga bruta}
-
\text{MMGD}
}
$$

Então vocês estimariam separadamente:

$$
\hat L_{\text{bruta}}(t)
$$

e

$$
\widehat{MMGD}(t)
$$

para finalmente calcular:

$$
\boxed{
\hat L_{\text{líquida}}(t)
=
\hat L_{\text{bruta}}(t)
-
\widehat{MMGD}(t)
}
$$

A competição quer que vocês **comparem essas duas estratégias**.

Isso é interessante porque o segundo modelo tenta explicitamente separar dois fenômenos com comportamentos bastante diferentes:

**consumo de energia** → atividade econômica, rotina das pessoas, horário, temperatura, dias úteis etc.

**geração solar distribuída** → radiação, nuvens, horário solar, capacidade instalada etc.

### Qual é o baseline?

O hackathon também fornece uma referência simples que vocês precisam superar.

O baseline é:

> usar a carga da **mesma hora e mesmo dia da semana anterior**.

Exemplo: para prever quarta-feira às 14h, utilizar quarta-feira passada às 14h.

Matematicamente:

$$
\hat y_t = y_{t-168}
$$

porque uma semana possui:

$$
24\times7=168\text{ horas}
$$

Esse baseline é mais competitivo do que parece, porque consumo elétrico possui uma periodicidade semanal muito forte.

### Como o modelo será avaliado?

A métrica indicada é **MAPE — Mean Absolute Percentage Error**:

$$
MAPE =
\frac{100}{n}
\sum_{t=1}^{n}
\left|
\frac{y_t-\hat y_t}{y_t}
\right|
$$

Ela mede o erro percentual médio entre a carga real e a carga prevista.

Por exemplo:

Carga real:

$$
10\,000\text{ MW}
$$

Previsão:

$$
9\,500\text{ MW}
$$

Erro:

$$
\frac{|10\,000-9\,500|}{10\,000}=5\%
$$

A imagem diz que a avaliação será feita **por submercado e por faixa horária**, dando **atenção especial às horas de sol**.

Isso faz bastante sentido porque justamente nesse intervalo a MMGD fotovoltaica produz energia e modifica mais fortemente a curva observada pelo ONS.

### Por que as horas solares são particularmente importantes?

Sem muita geração solar, uma curva de carga poderia ter aproximadamente este comportamento:

```text
Carga
  ^
  |                 /\
  |               /    \
  |______________/      \_______
        manhã     tarde   noite
```

Com muita geração solar distribuída, parte do consumo é atendida localmente durante o dia:

```text
Carga
  ^
  |       \          /
  |        \________/
  |________________________
        geração solar
```

O resultado pode se aproximar da conhecida **“duck curve”**, em que a carga líquida cai durante as horas solares e cresce rapidamente no final da tarde.

Isso faz com que **prever apenas o padrão histórico de consumo possa não ser suficiente**.

### Quais dados o hackathon sugere?

A própria imagem indica três fontes principais:

**ONS** — carga elétrica do SIN e dos submercados.

**ANEEL** — dados relacionados à MMGD, como capacidade instalada de geração distribuída.

**INMET** — dados meteorológicos.

Assim, conceitualmente vocês terão algo como:

$$
\text{Carga}
=
f(
\text{histórico},
\text{calendário},
\text{meteorologia},
\text{MMGD}
)
$$

Por exemplo:

```text
timestamp
submercado
carga_MW

hora
dia_semana
mes
feriado

temperatura
nebulosidade
precipitacao
radiacao_solar

capacidade_MMGD_MW
```

e posteriormente diversas features derivadas.

### Um detalhe importante: mudança metodológica em 2023

A imagem ainda dá um alerta:

> “Considerar feriados e a mudança metodológica de 2023; não comparar com o DESSEM sem alinhar o horizonte de previsão.”

Isso significa que existe uma **quebra estrutural/metodológica na série** que vocês precisarão investigar antes de simplesmente colocar todos os anos no mesmo modelo.

Em séries temporais, isso é importante porque o modelo pressupõe que:

$$
P(Y_t|X_t)
$$

tenha alguma estabilidade ao longo do tempo.

Se a forma de calcular a variável mudou, o modelo pode interpretar uma **mudança metodológica como uma mudança real no consumo elétrico**.

---

Portanto, eu resumiria o desafio assim:

> **Dado o histórico de carga elétrica de cada submercado do SIN, informações meteorológicas, calendário e evolução da micro e minigeração distribuída, prever a carga horária para D+1 e D+7. Além disso, comparar um modelo que prevê diretamente a carga líquida com outro que explicitamente separa carga bruta e geração distribuída.**

E existe uma consequência importante para a modelagem: **não é simplesmente um problema de forecasting de uma série temporal**. Na prática, é um problema de:

$$
\boxed{
\text{time series forecasting}
+
\text{variáveis exógenas}
+
\text{mudança estrutural}
+
\text{efeito da geração distribuída}
}
$$

Esse último ponto é provavelmente onde existe mais espaço para vocês construírem um diferencial interessante no hackathon.
