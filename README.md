# Klick

Ferramenta de captura de tela no estilo Lightshot: tudo começa selecionando uma área da tela; depois você escolhe a ação.
O plano completo está em [docs/PLANO.md](docs/PLANO.md).

## O que faz

Aperte **PrintScreen** (ou clique no ícone da bandeja), arraste a área e escolha na barra:

| Ação | Atalho na seleção | O que acontece |
| --- | --- | --- |
| Copiar | `Ctrl+C`, `Enter`, duplo clique | Imagem vai para o clipboard |
| Ler | `Ctrl+T` | Abre a leitura: arraste sobre as palavras e copie só o trecho, como no Google Lens |
| Marcar | `Ctrl+E` | Marca o print ali mesmo, sem abrir janela (ferramentas abaixo) |
| Salvar | `Ctrl+S` | Salva PNG/JPG (sugere `Imagens/Klick/Prints/klick_<data>.png`) |
| Pesquisar | `Ctrl+L` | Pesquisa a imagem no Google Lens, no navegador padrão |
| SQL | `Ctrl+Q` | Abre a janela de SQL: consulta formatada ou grade em Excel, CSV, INSERT e UPDATE |
| Gravar | `Ctrl+R` | Grava a área em MP4, com ou sem som |
| GIF | `Ctrl+G` | Grava a área em GIF, para colar em chat ou ticket |

Arrastar dentro da seleção move a área; botão direito limpa; `Esc` cancela. A lupa junto ao cursor mostra a posição
e a cor do pixel; `C` copia o código da cor.

**Atalhos globais**

- `PrintScreen`: capturar
- `Ctrl+Shift+T`: **OCR direto** (selecionou, soltou, o texto já está no clipboard)
- `Ctrl+Shift+R`: gravar área / parar gravação

**Depois de capturar** aparece um aviso no canto da tela com a miniatura e atalhos para marcar, ler ou salvar.

**Gravação:** antes de começar, um painel ao lado da seleção pergunta se vai ter som (sem som, do computador,
microfone ou os dois) e a qualidade (baixa 15 fps, média 30 fps, alta 60 fps); `Enter` começa e a escolha vira o
padrão. Durante a gravação aparece uma moldura vermelha e um controle com o tempo e o botão "Parar". Os dois ficam
fora do vídeo. O arquivo vai para `Gravações/` (ou `GIFs/`) e já fica no clipboard como arquivo, então é só colar no
chat. O som do computador é gravado pelo loopback do Windows, sem precisar ligar "Mixagem estéreo".

**Marcar:** o painel tem duas abas, Destacar e Analisar, com o nome, a tecla e o que cada ferramenta faz, além das
cores e da espessura (fina, média, grossa). Para destacar, `D` destaque (escurece o resto), `M` marca-texto, `A` seta, `N` passo (1, 2, 3) e `T`
texto (digitado direto); para analisar, `L` lupa, `P` ocultar, `R` medir em pixels e `I` conta-gotas. `C` troca a cor,
`Ctrl+Z` desfaz, `Enter` copia, `Ctrl+S` salva e `Esc` volta para a seleção. O ocultar usa blocos grandes de propósito,
para não dar para recuperar CPF ou CNPJ.

**Galeria:** tudo que você copia, salva, marca, lê ou grava fica guardado, em quatro coleções: Prints, Gravações, GIFs
e Leitura. A busca procura no texto que aparecia no print ("erro 500", "atencao" acha "Atenção"). `Enter` copia de
novo (gravações e GIFs vão como arquivo); na Leitura, abre o texto para selecionar. `Ctrl`+clique escolhe vários e
`Del` exclui de vez (gravações e GIFs: o arquivo também é apagado; "Remover da galeria" no menu mantém o arquivo). O
botão de pasta abre a pasta da coleção: `Prints/`, `Gravações/`, `GIFs/` e `Leitura/` dentro de `Imagens/Klick`. O
histórico fica em `%LOCALAPPDATA%\Klick\history` (as últimas 1000 capturas).

**Leitura:** além de copiar, `Pesquisar` busca o trecho no Google, `Google Lens` pesquisa a imagem e `Salvar .txt`
grava o texto em `Leitura/`.

**SQL:** janela própria para consulta e grade de resultado lidas de um print. Abre com `Ctrl+Q` na seleção, por "Ler
SQL ou tabela" no menu da bandeja, por "Abrir no SQL" na galeria ou pelos botões SQL e Tabela da leitura. Lê com os
dois motores (o RapidOCR ampliado e com as cores invertidas em fundo escuro, como num editor) e fica com a leitura mais
limpa.

- **Consulta:** o SQL consertado (`FR0M`, aspas curvas, `c. codcli`), formatado e colorido, editável; ao lado o tipo
  (SELECT, UPDATE…), as tabelas citadas e o print. "Formatar" refaz, "Texto lido" volta ao original.
- **Tabela:** a grade lida, editável (`Del` apaga linhas), com o nome da tabela, "primeira linha é o cabeçalho" e
  "vírgula decimal" (1.240,50 vira 1240.50). Copia como Excel, CSV (`;`), `INSERT` ou `UPDATE` (escolhendo a coluna do
  `WHERE`), com prévia ao vivo. "Salvar arquivo" grava `.sql`, `.csv` ou `.txt` em `Leitura/`.

O extra **SQL e tabelas** (ligado por padrão) mostra os botões SQL e Tabela na leitura quando o texto parece consulta
ou grade.

**Configurações** (engrenagem na galeria): lupa de pixels, guias de terço, aviso depois de copiar, salvar todo print
na pasta, leitura precisa, perguntar antes de gravar e o som/qualidade padrão, pasta do Klick, guardar histórico,
abrir com o Windows e os extras. As mudanças valem na hora.

**Visual:** a identidade é a "Painel": a estrutura do Windows 11 (barra lateral como no Explorador) com cara de
instrumento. Aço azulado no corpo, laranja só nas ações, leituras (tamanho, hora, contagens) em ciano e fonte mono,
botões em caixa alta. Fontes Barlow, Barlow Condensed e JetBrains Mono, que vão junto com o app. Cores e estilos ficam
em [klick/theme.py](klick/theme.py).

## Preferências

Ficam em `HKCU\Software\Klick\Klick`. A maioria muda pela tela de configurações; estas só pelo registro:

| Chave | Padrão | Para quê |
| --- | --- | --- |
| `save_dir` | `Imagens\Klick` | Pasta do Klick; cada tipo fica numa subpasta |
| `hotkeys/capture`, `hotkeys/ocr`, `hotkeys/record` | ver acima | Formato do pynput, ex.: `<ctrl>+<alt>+s` |
| `ocr/language` | perfil do Windows | Forçar idioma do OCR, ex.: `pt-BR` |
| `record/ffmpeg` | `ffmpeg` do PATH | Caminho do ffmpeg |
| `record/audio`, `record/quality` | `none`, `medium` | Som e qualidade padrão da gravação |
| `options/*` | ver configurações | Lupa, guias, avisos, extras etc. |
| `history/enabled`, `history/max_items` | `true`, `1000` | Histórico |

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
| `klick/app.py` | Entrada, bandeja, atalhos; liga a seleção às ações |
| `klick/capture.py` | Captura de cada monitor (mss, com fallback do Qt) e conversão lógico → físico |
| `klick/overlay.py` | Overlay de seleção, barra de ações e `CaptureSession` (um overlay por monitor) |
| `klick/actions.py` | Copiar imagem/texto/arquivo e salvar |
| `klick/ocr.py` | OCR via Windows.Media.Ocr, numa thread própria |
| `klick/editor.py` | Ferramentas de marcar (`Marker`), usadas na captura e na janela de marcar |
| `klick/reader.py` | Leitura estilo Lens: palavras com posição, seleção por arraste |
| `klick/lens.py` | Pesquisa no Google Lens (página local que envia a imagem) e no Google |
| `klick/sql.py` | SQL e tabelas: detecta, conserta, formata, colore e monta a grade (Excel, CSV, INSERT, UPDATE) |
| `klick/sql_ui.py` | Janela de SQL (abas Consulta e Tabela) |
| `klick/audio.py` | Som do computador na gravação (loopback do WASAPI) |
| `klick/settings_ui.py` | Tela de configurações |
| `klick/theme.py`, `icons.py`, `widgets.py` | Identidade Visor: cores, fontes, ícones, botões, aviso e confirmação |
| `klick/recorder.py` | Gravação com ffmpeg (gdigrab/x11grab) e conversão para GIF |
| `klick/recording_ui.py` | Moldura e controles da gravação, excluídos do vídeo |
| `klick/history.py`, `history_ui.py` | Histórico em SQLite com busca FTS5 e a galeria em quatro coleções |
| `klick/hotkeys.py` | Atalhos globais via pynput |
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
([packaging/klick.spec](packaging/klick.spec)) e o Inno Setup ([packaging/klick.iss](packaging/klick.iss)).

Para adicionar uma ação: crie o valor em `Action`, o botão em `Toolbar` e o tratamento em `KlickApp._on_finished`.
Com `CaptureSession(shots, direct_action=...)` a ação roda assim que o mouse é solto, sem mostrar a barra.
