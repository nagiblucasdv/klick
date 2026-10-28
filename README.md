# Klick

Ferramenta de captura de tela no estilo Lightshot: tudo começa selecionando uma área da tela; depois você escolhe a ação.
O plano completo está em [docs/PLANO.md](docs/PLANO.md).

## Estado atual

- Ícone na bandeja; clique nele ou aperte **PrintScreen** para capturar
- A tela é congelada e você arrasta o retângulo (funciona com vários monitores e escalas de DPI diferentes)
- **Copiar**: botão, `Ctrl+C`, `Enter` ou duplo clique na seleção
- **Texto (OCR)**: botão ou `Ctrl+T` extrai o texto da área e copia para o clipboard
- **OCR direto**: `Ctrl+Shift+T` (ou "Copiar texto" na bandeja) — selecionou, soltou, o texto já está no clipboard
- **Salvar**: botão ou `Ctrl+S` (sugere `Imagens/Klick/klick_<data>.png` e lembra a última pasta)
- Arrastar dentro da seleção move a área; botão direito limpa a seleção; `Esc` cancela

## Rodando (Windows)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
klick            # fica na bandeja
klick --capture  # já abre a seleção
klick --ocr      # já abre a seleção em modo OCR direto
```

O OCR usa o motor nativo do Windows (Windows.Media.Ocr, offline). Ele reconhece os idiomas instalados no perfil do
Windows; se aparecer "Nenhum idioma de OCR instalado", adicione o português em *Configurações > Hora e idioma > Idioma e
região*. Para forçar um idioma, grave a chave `ocr/language` (ex.: `pt-BR`) em `HKCU\Software\Klick\Klick`.

No Windows 11, a tecla PrintScreen abre a Ferramenta de Captura por padrão. Para o Klick receber a tecla, desative em
*Configurações > Acessibilidade > Teclado > "Usar a tecla Print Screen para abrir a captura de tela"*.

## Linux

Roda, mas com limitações: o OCR ainda é só do Windows, e no Wayland o `mss` e o `pynput` não funcionam, então a captura cai para o Qt (que pode vir
preta, dependendo do compositor) e não há atalho global. A alternativa é ligar `klick --oneshot` a um atalho do sistema.

## Testes

```bash
pytest
```

## Estrutura

| Módulo | Papel |
| --- | --- |
| `klick/app.py` | Entrada, bandeja, atalhos, orquestra a sessão de captura |
| `klick/capture.py` | Captura de cada monitor (mss, com fallback do Qt) e conversão lógico → físico |
| `klick/overlay.py` | Overlay de seleção, barra de ações e `CaptureSession` (um overlay por monitor) |
| `klick/actions.py` | Ações sobre a imagem: copiar, salvar |
| `klick/ocr.py` | OCR via Windows.Media.Ocr, numa thread própria |
| `klick/hotkeys.py` | Atalhos globais via pynput |
| `klick/config.py` | Preferências (QSettings): pasta de salvamento, atalhos |

Para adicionar uma ação nova (OCR, gravar): crie o valor em `Action`, o botão em `Toolbar` e o tratamento em
`KlickApp._on_finished`. Com `CaptureSession(shots, direct_action=...)` a ação roda assim que o mouse é solto, sem mostrar a
barra (é assim que o OCR direto funciona).
