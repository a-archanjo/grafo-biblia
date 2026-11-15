# Grafo de Referencias Biblicas

Projeto em Python para analisar as referencias cruzadas da Biblia, construir uma rede de versiculos e gerar visualizacoes interativas, rankings de conexoes e arquivos para exploracao no Gephi.

## Proposito do trabalho

A leitura de um texto costuma seguir a ordem dos capitulos e versiculos, mas as referencias cruzadas conectam passagens que podem estar distantes umas das outras. Representar essas relacoes como uma rede permite observar o conjunto de conexoes de uma vez, em vez de analisar cada referencia isoladamente. Essa perspectiva ajuda a explorar quais versiculos estao mais conectados e como as passagens se organizam na base coletada.

O objetivo do projeto e construir e explorar um grafo das referencias cruzadas biblicas. Cada versiculo e representado por um vertice, e cada referencia entre dois versiculos, por uma aresta. A analise atual procura responder a uma pergunta inicial: quais versiculos possuem mais conexoes diretas na rede e como essas conexoes podem ser apresentadas de forma legivel?

O trabalho e exploratorio: o grafo resume as relacoes presentes no conjunto de dados e complementa a leitura linear do texto, mas nao explica por si so o significado teologico de cada relacao. Em particular, os dados e o codigo atuais nao classificam as referencias como profecias, citacoes ou outros tipos de ligacao. Portanto, a visualizacao da rede nao deve ser tratada, isoladamente, como evidencia de cumprimento profetico.

## Modelo e analise atual

- Os vertices representam versiculos; as arestas representam referencias entre eles.
- O grafo e nao direcionado: uma referencia entre A e B e tratada como a mesma ligacao que B e A.
- Registros repetidos para o mesmo par sao consolidados, mantendo-se o maior valor de `Votes` (ou `Votos`), nao a soma.
- O ranking usa o grau do vertice, isto e, a quantidade de versiculos distintos ligados a ele. O valor de votos nao e usado como peso nesse ranking.
- A visualizacao HTML destaca os 15 versiculos de maior grau e, para cada um, mostra ate 8 conexoes com mais votos. A exportacao GEXF contem a rede completa.

Esse escopo permite identificar versiculos com muitas ligacoes diretas, mas ainda nao calcula distribuicao de grau, comunidades ou centralidade de intermediacao. Conclusoes sobre estrutura livre de escala, grupos tematicos ou versiculos que funcionam como pontes exigem analises adicionais e devem ser apresentadas como etapas futuras ate serem verificadas.

## Requisitos

- Python 3.10 ou superior
- Dependencias listadas em [`requirements.txt`](requirements.txt)

## Instalacao

No PowerShell, na pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Dados de entrada

Os arquivos de dados ficam na raiz do projeto e usam tabulacao como separador:

- `referencias_cruzadas_traduzidas.txt`: entrada usada por `main.py`. Contem as colunas `From Verse`, `To Verse` e `Votes`.
- `cross_references.txt`: arquivo original de referencias cruzadas, mantido junto aos dados do projeto.

Mantenha o arquivo traduzido na pasta do script ao executar `main.py`.

## Executar

Para processar os dados e gerar os resultados:

```powershell
python main.py
```

O script cria `grafo_referencias_biblicas.html`, `grafo_referencias_biblicas.png`, `top_100_versiculos_conexoes.csv` e `rede_completa_referencias_biblicas.gexf`. O PNG pode nao ser criado se o Kaleido ou o Chrome necessario a exportacao nao estiver disponivel; o HTML continua sendo gerado.

## Estrutura

- `main.py`: gera o grafo interativo, o ranking e a rede completa.
- `referencias_cruzadas_traduzidas.txt`: dados lidos pelo script.
- `cross_references.txt`: dados originais.

Os arquivos de visualizacao, rankings e redes exportadas sao resultados gerados e estao no `.gitignore`; eles podem ser recriados executando os scripts.