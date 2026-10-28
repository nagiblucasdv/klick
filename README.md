# Klick

Ferramenta de captura de tela no estilo Lightshot: tudo começa selecionando uma área da tela; depois você escolhe a ação.
O plano completo está em [docs/PLANO.md](docs/PLANO.md).

## Estado atual (MVP)

- Ícone na bandeja; clique nele ou aperte **PrintScreen** para capturar
- A tela é congelada e você arrasta o retângulo (funciona com vários monitores e escalas de DPI diferentes)
- **Copiar**: botão, `Ctrl+C`, `Enter` ou duplo clique na seleção
- **Salvar**: botão ou `Ctrl+S` (sugere `Imagens/Klick/klick_<data>.png` e lembra a última pasta)
- Arrastar dentro da seleção move a área; botão direito limpa a seleção; `Esc` cancela

## Rodando (Windows)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
klick            # fica na bandeja
klick --capture  # já abre a seleção
```

No Windows 11, a tecla PrintScreen abre a Ferramenta de Captura por padrão. Para o Klick receber a tecla, desative em
*Configurações > Acessibilidade > Teclado > "Usar a tecla Print Screen para abrir a captura de tela"*.

## Linux

Roda, mas com limitações: no Wayland o `mss` e o `pynput` não funcionam, então a captura cai para o Qt (que pode vir
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
| `klick/hotkeys.py` | Atalhos globais via pynput |
| `klick/config.py` | Preferências (QSettings): pasta de salvamento, atalhos |

Para adicionar uma ação nova (OCR, gravar): crie o valor em `Action`, o botão em `Toolbar` e o tratamento em
`KlickApp._on_finished`. O "OCR direto" já tem o caminho pronto: `CaptureSession(shots, direct_action=...)` executa a
ação assim que o mouse é solto, sem mostrar a barra.
