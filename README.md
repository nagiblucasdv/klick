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

Arrastar dentro da seleção move a área e os pontos nos cantos e lados ajustam o tamanho; um clique solto fora dela não apaga a seleção (só um arrasto começa outra);
botão direito limpa; `Esc` cancela. A lupa junto ao cursor mostra a posição e a cor do pixel; `C` copia o código da cor.

**Atalhos globais** (todos trocam em Configurações › Atalhos, clicando e apertando a combinação; vale tecla do FN do
notebook):

- `PrtSc`: print
- `F7`: gravar vídeo ou GIF / parar a gravação
- `Ctrl+Shift+T`: **ler texto direto** (selecionou, soltou, o texto já está no clipboard)
- `Ctrl+Shift+Espaço`: **painel de consultas**, como o `Windows + V` (veja abaixo)

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

**Galeria:** barra lateral escura com Capturar, Gravar, as coleções (Tudo, Prints, Gravações, GIFs, Leituras e
Análises), o filtro "Só na galeria", a pasta e as configurações. Cada cartão traz o selo "some em N dias" ou "na pasta".
A busca procura no texto que aparecia no print ("erro 500", "atencao" acha "Atenção"). `Enter` copia de novo (gravações
e GIFs vão como arquivo); em Leituras e Análises, abre o texto. `Ctrl+S` guarda na pasta e `Del` exclui de vez. O
histórico fica em `%LOCALAPPDATA%\Klick\history` (as últimas 1000 capturas).

**Leitura:** além de copiar, `Pesquisar` busca o trecho no Google, `Google Lens` pesquisa a imagem e `Salvar .txt`
grava o texto em `Leitura/`. Quando o texto é SQL, JSON ou uma grade, aparece "Abrir na Análise".

**Análise:** abre com `Ctrl+Q` na seleção, pela bandeja, pela galeria ou pela leitura. O Klick decide o que é (SQL,
JSON, tabela ou texto comum) e mostra só essa visão; "Ler como", em cima, troca se ele errar. Lê com os dois motores
(o RapidOCR ampliado e com as cores invertidas em fundo escuro, como num editor) e fica com a leitura mais limpa; o
texto é remontado pela posição das palavras, então a indentação do print fica. Cada correção do OCR aparece com uma
ondinha no texto, pisca uma vez ao chegar e fica na lista "Corrigido do OCR", de onde dá para desfazer. A conclusão diz
em uma frase o que aquilo é; a galeria guarda o texto final, com as suas correções.

- **SQL:** conserta `FR0M`, `SELEC7`, aspas curvas e `c. codcli` sem mexer em texto entre aspas, comentário nem na crase
  do MySQL. Formata (ou mostra como estava), lista as partes (tabelas com apelido, colunas, junções, filtros,
  agrupamento, ordem, limite) e confere: parêntese ou aspa aberta, `= NULL`, JOIN sem ON, vírgula antes do FROM,
  LEFT JOIN anulado pelo WHERE, INSERT com número errado de valores e, em vermelho, UPDATE ou DELETE sem WHERE. Com
  WHERE, "SELECT de conferência" copia as linhas que vão mudar e "Backup antes" copia um `CREATE TABLE …_bkp_<data> AS
  SELECT` delas.
- **JSON:** conserta só fora dos textos (aspas curvas ou simples, vírgula sobrando, `True`/`None`, chave sem aspas),
  formata ou compacta e, se estiver inválido, marca a linha do erro e diz o que falta. A árvore ao lado abre e fecha;
  clicar copia o caminho (`itens[0].cod`), duplo clique copia o valor. "Ver como tabela" transforma a lista de objetos
  numa grade.
- **Tabela:** as colunas saem do alinhamento de todas as linhas, então célula vazia não desloca a linha; o cabeçalho é
  detectado sozinho. Em cima, linhas, colunas e as somas (sem somar código). Célula de coluna de números lida com
  letra (`1O`) fica marcada com a sugestão (`10`) e "Trocar pelas sugestões" corrige. Copia como Excel, CSV (`;`),
  Markdown (para chat e chamado), `INSERT`, `UPDATE` (escolhendo a coluna do `WHERE`) ou JSON.

**Consultas** (Galeria › Biblioteca › Consultas): todas as consultas que você guarda, numa página só. Na Análise,
"Guardar consulta" pede um nome (sugere o tipo e as tabelas) e manda para cá; também dá para criar do zero ("Nova
consulta") e trazer os `.sql` que você já tem (Importar). À esquerda a lista, com as tabelas e quantas vezes cada uma foi
copiada (as mais usadas em cima); à direita a consulta, com as cores do SQL. O que você edita é guardado sozinho;
duplo clique ou `Ctrl+C` copia, `Del` exclui. A busca do topo procura no nome e no texto. Exportar junta todas num
`.sql` só, cada uma com o nome em comentário. Fica em `%LOCALAPPDATA%\Klick\consultas.db`, separada do histórico.

**Painel de consultas** (`Ctrl+Shift+Espaço`, em qualquer programa): como o `Windows + V`, só que das suas consultas.
Abre pequeno, junto do cursor de texto (ou do mouse), já pronto para digitar: digite para filtrar, setas escolhem,
`Enter` cola no programa em que você estava e `Ctrl+Enter` só copia. Some ao clicar fora; `Esc` fecha e devolve o foco.
As mais usadas ficam em cima. `Tab` troca para a aba **Tabelas**: as tabelas que o Klick aprendeu viram SELECT, INSERT
ou UPDATE com as colunas (setas para os lados trocam o modelo). Para aprender, ligue "Aprender tabelas e colunas" em
Configurações › Leitura e Análise: cada consulta que você copia ou guarda na Análise ensina as tabelas e colunas que
ela cita (`c.nome` com `FROM clientes c` diz que clientes tem nome). Ficam em `%LOCALAPPDATA%\Klick\estrutura.json`.

**Configurações** (engrenagem na galeria ou na bandeja): atalhos, onde salvar e por quanto tempo, pasta do Klick, lupa,
linhas de terço, aviso depois de copiar, perguntar antes de gravar e os padrões de formato/som/qualidade, leitura
precisa, Análise, aprender tabelas e colunas, guardar histórico e abrir com o Windows. As mudanças valem na hora.

**Visual:** a identidade é a "Plumagem", que vem do corvo do ícone. A moldura (barras laterais, painéis sobre a tela,
avisos, menus e a barra de título) é negro-azulada como a pena; o conteúdo é claro. O brilho furta-cor da pena
(verde-água, índigo, violeta) aparece só no que está ativo: a seleção, o foco, a ação principal. Cantos retos de 4 px,
e os painéis têm um corte em diagonal no canto de cima, como a ponta de uma pena. Bahnschrift nos títulos e números,
Segoe UI no texto e Consolas no código, todas do Windows. Movimento só onde mostra o que mudou: os cantos da seleção
encaixam ao soltar o mouse, o marcador da galeria desliza até a coleção, o aviso entra deslizando, a leitura varre o
print e as correções do OCR piscam ao chegar; com as animações do Windows desligadas, nada se mexe. Cores e estilos
ficam em [klick/theme.py](klick/theme.py).

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
| `klick/analysis/` | Motor da Análise: consertos do OCR, SQL, JSON, tabelas, o tipo e a estrutura aprendida |
| `klick/analysis_ui.py` | Janela da Análise |
| `klick/quick_ui.py`, `focus.py` | Painel de consultas (como o Windows + V) e o foco e a colagem no Windows |
| `klick/library.py`, `library_ui.py` | Biblioteca de consultas guardadas e a página Consultas da galeria |
| `klick/audio.py` | Som do computador na gravação (loopback do WASAPI) |
| `klick/settings_ui.py` | Configurações, com a gravação de atalhos |
| `klick/theme.py`, `icons.py`, `icon.py`, `widgets.py` | Identidade Plumagem: cores, fontes, formas, ícones, o corvo, botões, aviso |
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
