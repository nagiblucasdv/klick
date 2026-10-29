# Klick

Ferramenta de captura de tela no estilo Lightshot: tudo começa selecionando uma área da tela; depois você escolhe a ação.
O plano completo está em [docs/PLANO.md](docs/PLANO.md).

## O que faz

Aperte **PrintScreen** (ou clique no ícone da bandeja), arraste a área e escolha na barra:

| Ação | Atalho na seleção | O que acontece |
| --- | --- | --- |
| Copiar | `Ctrl+C`, `Enter`, duplo clique | Imagem vai para o clipboard |
| Texto | `Ctrl+T` | OCR da área; o texto vai para o clipboard |
| Editar | `Ctrl+E` | Abre o editor: seta, retângulo, texto, numeração (1, 2, 3) e pixelar |
| Salvar | `Ctrl+S` | Salva PNG/JPG (sugere `Imagens/Klick/klick_<data>.png`) |
| Gravar | `Ctrl+R` | Grava a área em MP4 |
| GIF | `Ctrl+G` | Grava a área em GIF, para colar em chat ou ticket |

Arrastar dentro da seleção move a área; botão direito limpa; `Esc` cancela.

**Atalhos globais**

- `PrintScreen`: capturar
- `Ctrl+Shift+T`: **OCR direto** (selecionou, soltou, o texto já está no clipboard)
- `Ctrl+Shift+R`: gravar área / parar gravação

**Gravação:** durante a gravação aparece uma moldura vermelha e um controle com o tempo e o botão "Parar". Os dois ficam
fora do vídeo. O arquivo vai para a pasta de capturas e já fica no clipboard como arquivo, então é só colar no chat.

**Editor:** atalhos `A` seta, `R` retângulo, `T` texto, `N` número, `P` pixelar, `Ctrl+Z` desfazer, `Ctrl+C` copiar,
`Ctrl+S` salvar. O pixelar usa blocos grandes de propósito, para não dar para recuperar CPF ou CNPJ.

**Histórico:** tudo que você copia, salva, edita ou passa no OCR fica guardado com o texto reconhecido. Em
"Histórico…" na bandeja, busque por qualquer palavra que aparecia no print ("erro 500", "atencao" acha "Atenção").
Duplo clique copia a imagem de novo. Dá para desligar em "Guardar histórico" (o padrão é guardar as últimas 1000
capturas). Ficam em `%LOCALAPPDATA%\Klick\history`.

## Instalação (Windows)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
winget install ffmpeg   # só para gravar
klick                   # fica na bandeja
```

Outras formas de abrir: `klick --capture`, `klick --ocr`, `klick --record`, `klick --history`.

**Antes de usar**

- No Windows 11, a tecla PrintScreen abre a Ferramenta de Captura. Desative em *Configurações > Acessibilidade >
  Teclado > "Usar a tecla Print Screen para abrir a captura de tela"*.
- O OCR usa o motor nativo do Windows (offline) com os idiomas do seu perfil. Se aparecer "Nenhum idioma de OCR
  instalado", adicione o português em *Configurações > Hora e idioma > Idioma e região*.

## Preferências

Ficam em `HKCU\Software\Klick\Klick` (sem tela de configurações por enquanto):

| Chave | Padrão | Para quê |
| --- | --- | --- |
| `save_dir` | `Imagens\Klick` | Pasta das capturas e gravações (atualiza ao salvar) |
| `hotkeys/capture`, `hotkeys/ocr`, `hotkeys/record` | ver acima | Formato do pynput, ex.: `<ctrl>+<alt>+s` |
| `ocr/language` | perfil do Windows | Forçar idioma do OCR, ex.: `pt-BR` |
| `record/ffmpeg` | `ffmpeg` do PATH | Caminho do ffmpeg |
| `record/fps` | `30` | Quadros por segundo da gravação |
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
| `klick/editor.py` | Editor de anotações e pixelar |
| `klick/recorder.py` | Gravação com ffmpeg (gdigrab/x11grab) e conversão para GIF |
| `klick/recording_ui.py` | Moldura e controles da gravação, excluídos do vídeo |
| `klick/history.py`, `history_ui.py` | Histórico em SQLite com busca FTS5 e a janela de busca |
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
