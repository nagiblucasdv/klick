# Ferramenta de Captura de Tela — Plano

Oct 28, 2026 · @Lucas Nagib

## Visão geral

Uma ferramenta estilo Lightshot em que tudo parte do mesmo passo: selecionar uma área da tela. Depois da seleção, você escolhe a ação.

- **Salvar** o print em arquivo
- **Copiar** o print para o clipboard
- **OCR**: extrair o texto da área e copiar direto, mais rápido que o Google Lens
- **Gravar** a tela só na área marcada

Detalhe de UX importante: um modo **"OCR direto"**, em que você seleciona e o texto já vai para o clipboard, sem abrir menu.

## Stack sugerida (Windows, Python)

| Parte | Ferramenta | Por quê |
| --- | --- | --- |
| Overlay de seleção + bandeja | PySide6 | Janela fullscreen transparente onde você arrasta o retângulo |
| Captura | `mss` | Rápido e funciona com vários monitores |
| OCR | Windows.Media.Ocr (pacote `winsdk`) | Offline, milissegundos, já reconhece pt-BR; mesmo motor da Ferramenta de Captura. Alternativa mais precisa: RapidOCR |
| Gravação | `ffmpeg -f gdigrab` | Usa `-offset_x`, `-offset_y` e `-video_size` da área marcada; sai MP4 direto |
| Atalho global | `keyboard` ou `pynput` | Ex.: PrintScreen para print, Ctrl+Shift+T para OCR direto |

## Ideias extras

**Úteis no dia a dia (principalmente em suporte)**

- **Blur/pixelar** área do print, para esconder CPF, CNPJ ou dados de cliente antes de mandar
- **Anotações:** seta, retângulo, texto e numeração (1, 2, 3) para passo a passo
- **GIF curto** em vez de MP4, para colar direto em chat ou ticket
- **OCR de tabela para CSV/Excel:** seleciona um grid na tela e cola como tabela de verdade
- **Pin na tela:** o print fica flutuando por cima das janelas, como no Snipaste

**Produtividade**

- **Histórico pesquisável:** capturas em SQLite com o texto do OCR indexado; busca por "erro 500" e acha o print da semana passada
- **Leitor de QR code e código de barras** na área selecionada
- **Traduzir** o texto capturado
- **Color picker:** pega o hex da cor sob o cursor
- **Captura com delay** (3s ou 5s) para pegar menus e tooltips

**Mais avançadas**

- **Scroll capture:** print de uma página inteira rolando
- **Gravar com áudio** do microfone ou do sistema
- **"Explicar com IA":** manda o print ou o texto do OCR para uma API (Claude, por exemplo) explicar um erro ou resumir

## Ordem sugerida

- [x] **MVP:** overlay de seleção, salvar e copiar
- [x] OCR para o clipboard
- [ ] Gravação com ffmpeg
- [ ] Blur, anotações e histórico
