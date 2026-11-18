"""ANÁLISE DA REDE DE REFERÊNCIAS CRUZADAS BÍBLICAS

O script preserva a rede por versículo e acrescenta a análise agregada por
capítulo. Os intervalos são tratados como uma única referência e atribuídos
ao capítulo inicial indicado no intervalo (sem expansão versículo a versículo).

Agregação por capítulo:
- cada par não direcionado e distinto de referências entre versículos conta uma vez;
- pares reversos/duplicados são eliminados;
- conexões entre versículos do mesmo capítulo não entram na rede entre capítulos;
- o peso da aresta entre capítulos é a quantidade de pares distintos de
  referências cruzadas entre esses capítulos.

Métricas:
- grau ponderado (strength): soma dos pesos das arestas incidentes;
- intermediação: centralidade exata no grafo não ponderado. O peso mede força/
  frequência de conexão, não distância; por isso não é usado como custo de caminho.
- densidade e clustering médio: calculados na topologia não ponderada.

Instalação:
    pip install pandas networkx plotly scipy
    pip install kaleido  # opcional, para exportar PNG

Coloque este arquivo e cross_references.txt na mesma pasta. O script também
reconhece cross_references(1).txt e referencias_cruzadas_traduzidas.txt.
"""
from pathlib import Path
import math
import re
import pandas as pd
import networkx as nx
import plotly.graph_objects as go
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import shortest_path, connected_components

PASTA = Path(__file__).resolve().parent
CANDIDATOS_ENTRADA = [
    PASTA / "cross_references.txt",
    PASTA / "cross_references(1).txt",
    PASTA / "referencias_cruzadas_traduzidas.txt",
]
ARQUIVO_HTML = PASTA / "grafo_biblico_interativo.html"
ARQUIVO_PNG = PASTA / "grafo_biblico.png"
ARQUIVO_CSV_VERSICULOS = PASTA / "ranking_versiculos_conexoes.csv"
ARQUIVO_GEXF_VERSICULOS = PASTA / "rede_biblica_completa.gexf"
ARQUIVO_CSV_CAPITULOS = PASTA / "ranking_capitulos.csv"
ARQUIVO_CSV_ARESTAS_CAPITULOS = PASTA / "arestas_capitulos.csv"
ARQUIVO_GEXF_CAPITULOS = PASTA / "rede_capitulos.gexf"
ARQUIVO_RESUMO = PASTA / "metricas_rede_capitulos.csv"

QUANTIDADE_DE_HUBS = 12
CONEXOES_POR_HUB = 4
SEMENTE = 42


def localizar_entrada():
    for caminho in CANDIDATOS_ENTRADA:
        if caminho.exists():
            return caminho
    raise FileNotFoundError(
        "Base não encontrada. Coloque cross_references.txt (ou um dos nomes "
        "alternativos reconhecidos) na mesma pasta do main.py."
    )


def carregar_dados(caminho):
    df = pd.read_csv(caminho, sep="\t")
    alternativas = [
        ("Versículo de origem", "Versículo relacionado", "Votos"),
        ("From Verse", "To Verse", "Votes"),
    ]
    colunas = None
    for origem, destino, votos in alternativas:
        if {origem, destino, votos}.issubset(df.columns):
            colunas = (origem, destino, votos)
            break
    if colunas is None:
        raise ValueError("Cabeçalhos não reconhecidos na base TXT.")
    df = df[list(colunas)].copy()
    df.columns = ["origem", "destino", "votos"]
    df = df.dropna(subset=["origem", "destino"])
    df["origem"] = df["origem"].astype(str).str.strip()
    df["destino"] = df["destino"].astype(str).str.strip()
    df["votos"] = pd.to_numeric(df["votos"], errors="coerce").fillna(0)
    df = df[(df.origem != "") & (df.destino != "") & (df.origem != df.destino)]
    return df


def chave_par(a, b):
    return tuple(sorted((str(a).strip(), str(b).strip())))


def criar_grafo_versiculos(df):
    pares = {}
    for linha in df.itertuples(index=False):
        a, b = chave_par(linha.origem, linha.destino)
        if a == b:
            continue
        pares[(a, b)] = max(pares.get((a, b), float("-inf")), float(linha.votos))
    G = nx.Graph()
    for (a, b), votos in pares.items():
        G.add_edge(a, b, votos=votos)
    return G, pares


def capitulo_da_referencia(referencia):
    """Extrai livro.capítulo; intervalos usam o primeiro endpoint."""
    inicio = str(referencia).strip().split("-")[0]
    partes = inicio.rsplit(".", 2)
    if len(partes) != 3 or not partes[1].isdigit() or not partes[2].isdigit():
        raise ValueError(f"Referência bíblica em formato inesperado: {referencia}")
    livro, capitulo, _versiculo = partes
    return f"{livro}.{int(capitulo)}"


def criar_grafo_capitulos(pares_versiculos):
    contagem = {}
    mesma_unidade = 0
    for a, b in pares_versiculos:
        ca, cb = capitulo_da_referencia(a), capitulo_da_referencia(b)
        if ca == cb:
            mesma_unidade += 1
            continue
        par = tuple(sorted((ca, cb)))
        contagem[par] = contagem.get(par, 0) + 1
    Gc = nx.Graph()
    for (a, b), peso in contagem.items():
        Gc.add_edge(a, b, weight=int(peso))
    return Gc, mesma_unidade


def clustering_medio_exato(G):
    """Clustering médio não ponderado por álgebra esparsa."""
    nos = list(G.nodes())
    idx = {no: i for i, no in enumerate(nos)}
    linhas, colunas = [], []
    for u, v in G.edges():
        i, j = idx[u], idx[v]
        linhas.extend((i, j)); colunas.extend((j, i))
    A = csr_matrix((np.ones(len(linhas)), (linhas, colunas)), shape=(len(nos), len(nos)))
    graus = np.asarray(A.sum(axis=1)).ravel()
    triangulos = np.asarray(A.multiply(A @ A).sum(axis=1)).ravel() / 2.0
    locais = np.divide(2.0 * triangulos, graus * (graus - 1),
                       out=np.zeros_like(graus, dtype=float), where=graus > 1)
    return float(locais.mean()), A, nos


def intermediacao_exata_nao_ponderada(A, nos):
    """Brandes exato para grafo não ponderado, com distâncias via SciPy.

    A matriz de distâncias é calculada em C/SciPy. A dependência de Brandes é
    acumulada por camadas, usando operações esparsas. Resultado normalizado
    conforme a convenção de NetworkX para grafos não direcionados.
    """
    n = len(nos)
    distancias = shortest_path(A, directed=False, unweighted=True, method="D")
    bc = np.zeros(n, dtype=float)
    for origem in range(n):
        d = distancias[origem]
        finitos = np.isfinite(d)
        maior = int(d[finitos].max())
        camadas = [np.flatnonzero(d == nivel) for nivel in range(maior + 1)]
        sigma = np.zeros(n, dtype=float)
        sigma[origem] = 1.0
        matrizes = []
        for nivel in range(1, maior + 1):
            anterior, atual = camadas[nivel - 1], camadas[nivel]
            B = A[anterior, :][:, atual]
            matrizes.append(B)
            sigma[atual] = B.T.dot(sigma[anterior])
        delta = np.zeros(n, dtype=float)
        for nivel in range(maior, 0, -1):
            anterior, atual = camadas[nivel - 1], camadas[nivel]
            B = matrizes[nivel - 1]
            delta[anterior] += sigma[anterior] * B.dot((1.0 + delta[atual]) / sigma[atual])
        delta[origem] = 0.0
        bc += delta
    if n > 2:
        bc /= ((n - 1) * (n - 2))
    return bc


def analisar_capitulos(Gc, mesma_unidade):
    clustering, A, nos = clustering_medio_exato(Gc)
    intermediacao = intermediacao_exata_nao_ponderada(A, nos)
    grau = dict(Gc.degree())
    grau_ponderado = dict(Gc.degree(weight="weight"))
    ranking = pd.DataFrame({
        "Capítulo": nos,
        "Grau": [grau[n] for n in nos],
        "Grau ponderado": [int(grau_ponderado[n]) for n in nos],
        "Intermediação exata normalizada": intermediacao,
        "Clustering local": [nx.clustering(Gc, n) for n in nos],
    })
    ranking = ranking.sort_values(
        ["Intermediação exata normalizada", "Capítulo"],
        ascending=[False, True]
    ).reset_index(drop=True)
    ranking.insert(1, "Ranking intermediação", np.arange(1, len(ranking) + 1))
    ranking["Ranking grau ponderado"] = ranking["Grau ponderado"].rank(
        method="min", ascending=False
    ).astype(int)
    ranking.to_csv(ARQUIVO_CSV_CAPITULOS, index=False, encoding="utf-8-sig")

    arestas = pd.DataFrame([
        {"Capítulo A": u, "Capítulo B": v, "Peso (referências distintas)": int(d["weight"])}
        for u, v, d in Gc.edges(data=True)
    ]).sort_values(["Peso (referências distintas)", "Capítulo A", "Capítulo B"], ascending=[False, True, True])
    arestas.to_csv(ARQUIVO_CSV_ARESTAS_CAPITULOS, index=False, encoding="utf-8-sig")
    nx.write_gexf(Gc, ARQUIVO_GEXF_CAPITULOS)

    componentes = connected_components(A, directed=False, return_labels=False)
    resumo = pd.DataFrame([
        {"Métrica": "Vértices (capítulos)", "Valor": Gc.number_of_nodes()},
        {"Métrica": "Arestas (pares de capítulos)", "Valor": Gc.number_of_edges()},
        {"Métrica": "Densidade", "Valor": nx.density(Gc)},
        {"Métrica": "Clustering médio não ponderado", "Valor": clustering},
        {"Métrica": "Componentes conexas", "Valor": int(componentes)},
        {"Métrica": "Pares de referências no mesmo capítulo excluídos", "Valor": int(mesma_unidade)},
        {"Métrica": "Soma dos pesos das arestas", "Valor": int(arestas["Peso (referências distintas)"].sum())},
    ])
    resumo.to_csv(ARQUIVO_RESUMO, index=False, encoding="utf-8-sig")
    return ranking, resumo


def gerar_ranking_versiculos(G):
    ranking = pd.DataFrame([
        {"Versículo": no, "Número de conexões": grau}
        for no, grau in G.degree()
    ]).sort_values(["Número de conexões", "Versículo"], ascending=[False, True]).reset_index(drop=True)
    ranking.to_csv(ARQUIVO_CSV_VERSICULOS, index=False, encoding="utf-8-sig")
    return ranking


def gerar_visualizacao(G, ranking):
    principais = ranking.head(QUANTIDADE_DE_HUBS)["Versículo"].tolist()
    subgrafo = nx.Graph(); subgrafo.add_nodes_from(principais)
    for hub in principais:
        vizinhos = sorted(G[hub].items(), key=lambda item: item[1].get("votos", 0), reverse=True)[:CONEXOES_POR_HUB]
        for vizinho, atributos in vizinhos:
            subgrafo.add_edge(hub, vizinho, **atributos)
    posicoes = nx.spring_layout(subgrafo, seed=SEMENTE, k=0.75, iterations=120)
    edge_x, edge_y = [], []
    for origem, destino in subgrafo.edges():
        x0, y0 = posicoes[origem]; x1, y1 = posicoes[destino]
        edge_x.extend([x0, x1, None]); edge_y.extend([y0, y1, None])
    trace_arestas = go.Scatter(x=edge_x, y=edge_y, mode="lines",
        line=dict(width=0.8, color="rgba(120,130,145,0.45)"), hoverinfo="none", name="Ligações")
    nos = list(subgrafo.nodes()); graus = dict(G.degree()); valores = [graus[n] for n in nos]
    maior_grau = max(graus.values()) if graus else 1
    tamanhos = [10 + 48 * math.sqrt(graus[n] / maior_grau) for n in nos]
    trace_nos = go.Scatter(
        x=[posicoes[n][0] for n in nos], y=[posicoes[n][1] for n in nos], mode="markers+text",
        text=nos, textposition="top center", textfont=dict(size=13, color="#263238"),
        marker=dict(size=tamanhos, color=valores, colorscale="YlOrRd", showscale=True,
            colorbar=dict(title=dict(text="Nº de<br>conexões", font=dict(size=15)), tickfont=dict(size=13), thickness=16),
            line=dict(width=1, color="white"), sizemode="diameter", opacity=0.9),
        customdata=[[graus[n], "Principal" if n in principais else "Relacionado"] for n in nos],
        hovertemplate="<b>%{text}</b><br>Classificação: %{customdata[1]}<br>Total de conexões na rede: %{customdata[0]}<extra></extra>",
        name="Versículos")
    fig = go.Figure(data=[trace_arestas, trace_nos])
    fig.update_layout(title="Referências cruzadas bíblicas<br><sup>O tamanho e a cor dos círculos representam o número de conexões do versículo na rede completa.</sup>",
        hoverlabel=dict(font=dict(size=15)), showlegend=False, hovermode="closest", template="plotly_white",
        title_font=dict(size=25), margin=dict(l=25, r=35, t=125, b=25), xaxis=dict(visible=False), yaxis=dict(visible=False), height=1000)
    fig.write_html(ARQUIVO_HTML, include_plotlyjs=True)
    try:
        fig.write_image(ARQUIVO_PNG, width=1900, height=1300, scale=2)
    except Exception as erro:
        print(f"PNG não gerado (instale kaleido se necessário): {erro}")


def main():
    entrada = localizar_entrada()
    print(f"Base: {entrada.name}")
    df = carregar_dados(entrada)
    G, pares = criar_grafo_versiculos(df)
    ranking_versiculos = gerar_ranking_versiculos(G)
    gerar_visualizacao(G, ranking_versiculos)
    nx.write_gexf(G, ARQUIVO_GEXF_VERSICULOS)

    Gc, mesma_unidade = criar_grafo_capitulos(pares)
    ranking_capitulos, resumo = analisar_capitulos(Gc, mesma_unidade)

    print("\nREDE POR VERSÍCULO")
    print(f"Registros lidos: {len(df):,}")
    print(f"Vértices: {G.number_of_nodes():,} | Arestas: {G.number_of_edges():,}")
    print("\nREDE AGREGADA POR CAPÍTULO")
    print(resumo.to_string(index=False))
    print("\nTOP 8 POR INTERMEDIAÇÃO EXATA")
    print(ranking_capitulos[["Capítulo", "Intermediação exata normalizada", "Grau ponderado"]].head(8).to_string(index=False))
    print("\nTOP 8 POR GRAU PONDERADO")
    print(ranking_capitulos.sort_values("Grau ponderado", ascending=False)[["Capítulo", "Grau ponderado", "Intermediação exata normalizada"]].head(8).to_string(index=False))
    print("\nArquivos gerados: ranking_versiculos_conexoes.csv, ranking_capitulos.csv, arestas_capitulos.csv, metricas_rede_capitulos.csv, rede_biblica_completa.gexf, rede_capitulos.gexf, grafo_biblico_interativo.html e, se kaleido estiver instalado, grafo_biblico.png")

if __name__ == "__main__":
    main()
