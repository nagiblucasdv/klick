# Klick

Ferramenta de captura de tela no estilo Lightshot: tudo começa selecionando uma área da tela; depois você escolhe a ação.
Criado por Lucas Nagib. O plano completo está em [docs/PLANO.md](docs/PLANO.md).

## O que faz

**Print (`PrtSc`)** é só imagem. Arraste a área e escolha na barra:

| Ação | Atalho na seleção | O que acontece |
| --- | --- | --- |
| Copiar | `Ctrl+C`, `Enter`, duplo clique | Imagem vai para o clipboard |
| Salvar | `Ctrl+S` | Salva PNG/JPG (sugere `Imagens/Klick/Prints/klick_<data>.png`) |
| Editar | `Ctrl+E` | Edita o print ali mesmo, sem abrir janela (ferramentas abaixo) |
| Ler | `Ctrl+T` | Abre a leitura: arraste sobre as palavras e copie só o trecho, como no Google Lens |
| Pesquisar | `Ctrl+L` | Pesquisa a imagem no Google Lens, no navegador padrão |
| Análise | `Ctrl+Q` | Abre a Análise: consulta SQL, JSON ou grade de resultado |

**Gravar (`F7`)** seleciona a área e abre o painel de gravação: **Vídeo (MP4) ou GIF**, som (sem som, computador,
microfone ou ambos) e qualidade (baixa 15 fps, média 30 fps, alta 60 fps). `Enter` começa e a escolha vira o padrão;
apertar o atalho de novo para. A moldura vermelha e o controle com o tempo ficam fora do vídeo. O arquivo já fica no
clipboard como arquivo, então é só colar no chat. O som do computador é gravado pelo loopback do Windows.

Arrastar dentro da seleção move a área; um clique solto fora dela não apaga a seleção (só um arrasto começa outra);
botão direito limpa; `Esc` cancela. A lupa junto ao cursor mostra a posição e a cor do pixel; `C` copia o código da cor.

**Atalhos globais** (todos trocam em Configurações › Atalhos, clicando e apertando a combinação; vale tecla do FN do
notebook):

- `PrtSc`: print
- `F7`: gravar vídeo ou GIF / parar a gravação
- `Ctrl+Shift+T`: **ler texto direto** (selecionou, soltou, o texto já está no clipboard)

**Depois de copiar** aparece um aviso no canto da tela com a miniatura e atalhos para editar, ler, pesquisar e guardar.

**Editar imagem:** uma barra só, com todas as ferramentas à vista e o que cada uma faz embaixo. Formas: `B` caixa, `O`
elipse, `A` seta, `L` linha. Destacar: `D` destaque (escurece o resto), `M` marca-texto, `F` caneta, `N` número (1, 2,
3) e `T` texto (digitado direto). Proteger e analisar: `P` pixelar, `U` desfocar, `Z` lupa, `R` medir em pixels e `I`
conta-gotas. Sete cores (`C` troca), três espessuras, `Ctrl+Z` desfaz, `Enter` copia, `Ctrl+S` salva e `Esc` volta. O
pixelar usa blocos grandes de propósito, para não dar para recuperar CPF ou CNPJ.

**Onde fica salvo:** cada tipo escolhe "na pasta" ou "só na galeria". Por padrão prints e leituras ficam só na galeria
e gravações e GIFs vão para a pasta. O que está só na galeria some depois de 7 dias (1, 7, 30 dias ou nunca); guardar
na pasta (`Ctrl+S` na galeria, ou "Guardar" no aviso) tira do prazo: o print vira PNG em `Prints/`, a leitura vira `.txt`
em `Leitura/` e a gravação sai da pasta interna da galeria para `Gravações/` ou `GIFs/`.

**Galeria:** menu lateral de vidro com Capturar, Gravar, as coleções (Tudo, Prints, Gravações, GIFs, Leituras e
Análises), o filtro "Só na galeria", a pasta e as configurações. Cada cartão traz o selo "some em N dias" ou "na pasta".
A busca procura no texto que aparecia no print ("erro 500", "atencao" acha "Atenção"). `Enter` copia de novo (gravações
e GIFs vão como arquivo); em Leituras e Análises, abre o texto. `Ctrl+S` guarda na pasta e `Del` exclui de vez. O
histórico fica em `%LOCALAPPDATA%\Klick\history` (as últimas 1000 capturas).

**Leitura:** além de copiar, `Pesquisar` busca o trecho no Google, `Google Lens` pesquisa a imagem e `Salvar .txt`
grava o texto em `Leitura/`. Quando o texto é SQL, JSON ou uma grade, aparece "Abrir na Análise".

**Análise:** janela própria para o que foi lido de um print, com o painel da direita explicando o que achou. Abre com
`Ctrl+Q` na seleção, pela bandeja, pela galeria ou pela leitura, já na aba certa. Lê com os dois motores (o RapidOCR
ampliado e com as cores invertidas em fundo escuro, como num editor) e fica com a leitura mais limpa.

- **Consulta SQL:** consertada (`FR0M`, aspas curvas, `c. codcli`), formatada e colorida; ao lado o tipo, as tabelas,
  as junções, os filtros do `WHERE`, o agrupamento e a ordem.
- **JSON:** consertado (aspas curvas ou simples, vírgula sobrando, `True`/`None`, chave sem aspas), validado com a linha
  e a coluna do erro, formatado ou compactado; ao lado as chaves, os itens, a profundidade e os campos.
- **Tabela:** a grade editável (`Del` apaga linhas), com nome da tabela, "1ª linha é cabeçalho" e "vírgula decimal".
  Copia como Excel, CSV (`;`), `INSERT` ou `UPDATE` (escolhendo a coluna do `WHERE`). Ao lado, o resumo de cada coluna:
  tipo, preenchidos, diferentes e, nos números, soma, média, mínimo e máximo ("Copiar resumo").

**Configurações** (engrenagem na galeria ou na bandeja): atalhos, onde salvar e por quanto tempo, pasta do Klick, lupa,
linhas de terço, aviso depois de copiar, perguntar antes de gravar e os padrões de formato/som/qualidade, leitura
precisa, Análise, guardar histórico e abrir com o Windows. As mudanças valem na hora.

**Visual:** a identidade é a "Névoa": vidro claro sobre uma bruma verde-petróleo e areia, verde-petróleo só nas ações, vermelho só para gravar e
âmbar para o que é temporário. A fonte é a do Windows (Segoe UI), nítida em qualquer tamanho, com a hierarquia feita pelo peso, números em Consolas, cantos
arredondados e botões em pílula. Por cima da tela, os painéis mostram a tela congelada desfocada por trás. O ícone é o
selo com a cabeça do corvo, com o olho na forma da mira de captura. Cores e estilos ficam em
[klick/theme.py](klick/theme.py).

## Preferências

Ficam em `HKCU\Software\Klick\Klick`. A maioria muda pela tela de configurações; estas só pelo registro:

| Chave | Padrão | Para quê |
| --- | --- | --- |
| `ocr/language` | perfil do Windows | Forçar idioma do OCR, ex.: `pt-BR` |
| `record/ffmpeg` | `ffmpeg` junto do app ou do PATH | Caminho do ffmpeg |
| `history/max_items` | `1000` | Quantas capturas a galeria guarda |

As outras (`save_dir`, `hotkeys/*`, `save/*`, `record/*`, `options/*`, `history/enabled`) são as da tela de
configurações. Os atalhos usam o formato do pynput (`<ctrl>+<alt>+s`, `<f7>`, ou `<255>` para o código de uma tecla).

## Linux

Roda com limitações: o OCR é só do Windows, e no Wayland o `mss`, o `pynput` e o `x11grab` não funcionam (a captura cai
para o Qt e pode vir preta). Em X11 funciona, inclusive a gravação. Sem atalho global, ligue `klick --oneshot` a um
atalho do sistema.

## Desenvolvimento

```bash
pytest
```

Os testes rodam sem tela (`QT_QPA_PLATFORM=offscreen`) e usam preferências e histórico temporários. Os de gravação usam
o ffmpeg de verdade, com uma fonte de vídeo sintética no lugar da tela, e são pulados se ele não estiver instalado.

| Módulo | Papel |
| --- | --- |
| `klick/app.py` | Entrada, bandeja, atalhos; liga a seleção às ações e aplica onde salvar |
| `klick/capture.py` | Captura de cada monitor (mss, com fallback do Qt) e conversão lógico → físico |
| `klick/overlay.py` | Overlay de seleção (modos print e gravar), barra de ações e `CaptureSession` |
| `klick/actions.py` | Copiar imagem/texto/arquivo e salvar |
| `klick/ocr.py` | OCR via Windows.Media.Ocr e RapidOCR, em threads próprias |
| `klick/editor.py` | Editar imagem (`Marker` e `EditBar`), usado na captura e na janela de editar |
| `klick/reader.py` | Leitura estilo Lens: palavras com posição, seleção por arraste |
| `klick/lens.py` | Pesquisa no Google Lens (página local que envia a imagem) e no Google |
| `klick/sql.py` | SQL, JSON e tabelas: detecta, conserta, formata, colore, resume e converte |
| `klick/sql_ui.py` | Janela de Análise (abas Consulta SQL, JSON e Tabela) |
| `klick/audio.py` | Som do computador na gravação (loopback do WASAPI) |
| `klick/settings_ui.py` | Configurações, com a gravação de atalhos |
| `klick/theme.py`, `icons.py`, `icon.py`, `widgets.py` | Identidade Névoa: cores, fontes, ícones, o corvo, botões, aviso |
| `klick/recorder.py` | Gravação com ffmpeg (gdigrab/x11grab) e conversão para GIF |
| `klick/recording_ui.py` | Painel de gravar (vídeo ou GIF) e a moldura e os controles, excluídos do vídeo |
| `klick/history.py`, `history_ui.py` | Histórico em SQLite com busca FTS5, temporários e a galeria com menu lateral |
| `klick/hotkeys.py` | Atalhos globais via pynput e o gravador de atalho |
| `klick/config.py` | Preferências (QSettings) |
| `klick/single.py` | Instância única: abrir de novo repassa o comando para o Klick que já está na bandeja |

### Instalador

```powershell
winget install Gyan.FFmpeg.Essentials JRSoftware.InnoSetup
.\packaging\build.ps1
```

Gera `dist\Klick-Setup-<versão>.exe`: instala em `%LOCALAPPDATA%\Programs\Klick` sem pedir administrador, com o
ffmpeg junto, atalho no Menu Iniciar, opção de iniciar com o Windows e de liberar a tecla PrintScreen da Ferramenta de
Captura. O script cria um venv próprio (`.venv-build`, Python 3.12), roda os testes, o PyInstaller
([packaging/klick.spec](packaging/klick.spec), que deixa de fora o que vem junto sem uso) e o Inno Setup
([packaging/klick.iss](packaging/klick.iss)).

Para adicionar uma ação: crie o valor em `Action`, o botão em `Toolbar` e o tratamento em `KlickApp._on_finished`.
Com `CaptureSession(shots, direct_action=...)` a ação roda assim que o mouse é solto, sem mostrar a barra.
