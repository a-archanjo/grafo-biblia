"""
GRAFO DE REFERÊNCIAS CRUZADAS BÍBLICAS
O tamanho de cada círculo representa o número de conexões do versículo
na rede completa. Quanto maior o círculo, mais conexões ele possui.

Instalação:
    pip install pandas networkx plotly

Opcional para exportar PNG:
    pip install -U kaleido

Coloque este script e o TXT na mesma pasta.
Por padrão, usa referencias_cruzadas_traduzidas.txt.
"""

from pathlib import Path
import math
import pandas as pd
import networkx as nx
import plotly.graph_objects as go

PASTA = Path(__file__).resolve().parent

# Arquivo TXT traduzido. Também aceita o arquivo original em inglês.
ARQUIVO_ENTRADA = PASTA / "referencias_cruzadas_traduzidas.txt"

ARQUIVO_HTML = PASTA / "grafo_biblico_interativo.html"
ARQUIVO_PNG = PASTA / "grafo_biblico.png"
ARQUIVO_CSV = PASTA / "ranking_versiculos_conexoes.csv"
ARQUIVO_GEXF = PASTA / "rede_biblica_completa.gexf"

QUANTIDADE_DE_HUBS = 15
CONEXOES_POR_HUB = 8
SEMENTE = 42


def carregar_dados(caminho):
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}\n"
            "Coloque o TXT na mesma pasta deste script."
        )

    df = pd.read_csv(caminho, sep="\t")

    # Reconhece tanto os cabeçalhos em português quanto os originais.
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
        raise ValueError(
            "Não reconheci os cabeçalhos. Esperava as colunas "
            "'Versículo de origem', 'Versículo relacionado', 'Votos' "
            "ou 'From Verse', 'To Verse', 'Votes'."
        )

    df = df[list(colunas)].copy()
    df.columns = ["origem", "destino", "votos"]

    df = df.dropna(subset=["origem", "destino"])
    df["origem"] = df["origem"].astype(str).str.strip()
    df["destino"] = df["destino"].astype(str).str.strip()
    df["votos"] = pd.to_numeric(
        df["votos"], errors="coerce"
    ).fillna(0)

    df = df[
        (df["origem"] != "")
        & (df["destino"] != "")
        & (df["origem"] != df["destino"])
    ]

    return df


def criar_grafo(df):
    print("Construindo a rede...")

    # Grafo não direcionado: A-B e B-A contam como uma ligação.
    pares = df.copy()
    pares["A"] = pares[["origem", "destino"]].min(axis=1)
    pares["B"] = pares[["origem", "destino"]].max(axis=1)

    # Evita duplicar ligações reversas; preserva o maior valor de votos.
    arestas = (
        pares.groupby(["A", "B"], as_index=False)
        .agg(Votos=("votos", "max"))
    )

    G = nx.Graph()
    for linha in arestas.itertuples(index=False):
        G.add_edge(linha.A, linha.B, votos=float(linha.Votos))

    return G


def calcular_ranking(G):
    ranking = pd.DataFrame(
        [
            {"Versículo": no, "Número de conexões": grau}
            for no, grau in G.degree()
        ]
    )

    ranking = ranking.sort_values(
        ["Número de conexões", "Versículo"],
        ascending=[False, True]
    ).reset_index(drop=True)

    ranking.to_csv(
        ARQUIVO_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    return ranking


def gerar_visualizacao(G, ranking):
    print("Preparando visualização...")

    principais = ranking.head(QUANTIDADE_DE_HUBS)[
        "Versículo"
    ].tolist()

    # Para facilitar a leitura, o HTML mostra os hubs e suas
    # conexões mais votadas. O GEXF exportado abaixo contém tudo.
    subgrafo = nx.Graph()
    subgrafo.add_nodes_from(principais)

    for hub in principais:
        vizinhos = sorted(
            G[hub].items(),
            key=lambda item: item[1].get("votos", 0),
            reverse=True
        )[:CONEXOES_POR_HUB]

        for vizinho, atributos in vizinhos:
            subgrafo.add_edge(hub, vizinho, **atributos)

    posicoes = nx.spring_layout(
        subgrafo,
        seed=SEMENTE,
        k=0.75,
        iterations=120
    )

    # Linhas das conexões
    edge_x, edge_y = [], []
    for origem, destino in subgrafo.edges():
        x0, y0 = posicoes[origem]
        x1, y1 = posicoes[destino]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    trace_arestas = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=0.8, color="rgba(120,130,145,0.45)"),
        hoverinfo="none",
        name="Ligações"
    )

    # Nós: o grau é calculado na REDE COMPLETA, não apenas no recorte.
    nos = list(subgrafo.nodes())
    graus = dict(G.degree())
    valores = [graus[n] for n in nos]
    maior_grau = max(graus.values()) if graus else 1

    # Escala de tamanho suavizada: evita que o maior nó esconda os demais.
    # Nós com mais conexões ficam claramente maiores.
    tamanhos = [
        10 + 48 * math.sqrt(graus[n] / maior_grau)
        for n in nos
    ]

    # Exibe o nome de TODOS os versículos diretamente no grafo.
    # Os rótulos menores ajudam a manter a leitura sem perder os nomes.
    rotulos = nos

    trace_nos = go.Scatter(
        x=[posicoes[n][0] for n in nos],
        y=[posicoes[n][1] for n in nos],
        mode="markers+text",
        text=rotulos,
        textposition="top center",
        textfont=dict(size=13, color="#263238"),
        marker=dict(
            size=tamanhos,
            color=valores,
            colorscale="YlOrRd",
            showscale=True,
            colorbar=dict(
                title=dict(
                    text="Nº de<br>conexões",
                    font=dict(size=15)
                ),
                tickfont=dict(size=13),
                thickness=16
            ),
            line=dict(width=1, color="white"),
            sizemode="diameter",
            opacity=0.9
        ),
        customdata=[
            [graus[n], "Principal" if n in principais else "Relacionado"]
            for n in nos
        ],
        hovertemplate=(
            "<b>%{text}</b>"
            "<br>Classificação: %{customdata[1]}"
            "<br>Total de conexões na rede: %{customdata[0]}"
            "<extra></extra>"
        ),
        name="Versículos"
    )

    fig = go.Figure(data=[trace_arestas, trace_nos])

    fig.update_layout(
        title=(
            "Referências cruzadas bíblicas"
            "<br><sup>"
            "Os nomes de todos os versículos estão visíveis. "
            "Quanto maior e mais vermelho o círculo, maior o número de conexões."
            "</sup>"
        ),
        hoverlabel=dict(font=dict(size=15)),
        showlegend=False,
        hovermode="closest",
        template="plotly_white",
        title_font=dict(size=25),
        margin=dict(l=25, r=35, t=125, b=25),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=1000
    )

    fig.write_html(ARQUIVO_HTML, include_plotlyjs=True)
    print(f"HTML interativo salvo: {ARQUIVO_HTML}")

    try:
        fig.write_image(
            ARQUIVO_PNG,
            width=1900,
            height=1300,
            scale=2
        )
        print(f"Imagem PNG salva: {ARQUIVO_PNG}")
    except Exception as erro:
        print("PNG não foi gerado. O HTML está pronto.")
        print("Para habilitar PNG, execute: pip install -U kaleido")
        print(f"Detalhe: {erro}")


def main():
    print("=" * 60)
    print("GRAFO DE REFERÊNCIAS CRUZADAS BÍBLICAS")
    print("=" * 60)

    df = carregar_dados(ARQUIVO_ENTRADA)
    G = criar_grafo(df)
    ranking = calcular_ranking(G)

    gerar_visualizacao(G, ranking)

    print("Exportando rede completa para Gephi...")
    nx.write_gexf(G, ARQUIVO_GEXF)

    print("\nRESUMO DA REDE")
    print(f"Registros lidos: {len(df):,}")
    print(f"Versículos (nós): {G.number_of_nodes():,}")
    print(f"Ligações únicas (arestas): {G.number_of_edges():,}")

    print("\nTOP 15 VERSÍCULOS COM MAIS CONEXÕES:")
    print(ranking.head(15).to_string(index=False))

    print("\nArquivos gerados:")
    print(f"- {ARQUIVO_HTML.name}")
    print(f"- {ARQUIVO_PNG.name}")
    print(f"- {ARQUIVO_CSV.name}")
    print(f"- {ARQUIVO_GEXF.name}")


if __name__ == "__main__":
    main()
