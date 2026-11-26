# MedCerto API 💊

**O catálogo de remédios por trás do MedCerto.**

API REST em Django que fornece ao app [MedCerto](https://github.com/fredeerico/MedCerto) a busca de nomes em um catálogo de **6.012 medicamentos da ANVISA**, além de contas de usuário com login por token.

> Projeto acadêmico da UC **Usabilidade e Desenvolvimento WEB (A3)** · Grupo 02 · 2026/02

🌐 **API no ar:** [medcerto-api.onrender.com](https://medcerto-api.onrender.com/api/docs/) · 📱 **App:** [github.com/fredeerico/MedCerto](https://github.com/fredeerico/MedCerto) · 📄 **Documentação:** [GitBook do projeto](https://a3-medcerto-grupo-02.gitbook.io/a3-medcerto-grupo-02)

---

## ✅ Funcionalidades

- **Catálogo de medicamentos:** busca por nome (`?name=`), paginada de 20 em 20, com tarja, classe terapêutica e registro ANVISA
- **Carga automática:** a cada inicialização o catálogo é recarregado da planilha `data/medications.xlsx`
- **Importação pelo admin:** envio de uma nova planilha `.xlsx` para atualizar o catálogo
- **Usuários:** cadastro, login com token e troca de senha com código enviado por e-mail
- **Documentação interativa** (Swagger) gerada automaticamente

## 🔗 Rotas principais

| Método | Rota | Para quê |
|---|---|---|
| `POST` | `/api/users/` | Criar conta |
| `POST` | `/api/login/` | Entrar e receber o token |
| `GET` | `/api/medications/?name=dipirona` | Buscar remédios (exige token) |
| `POST` | `/api/medications/import/` | Importar planilha (só admin) |
| `POST` | `/api/users/password/change/code/` | Pedir código para trocar a senha |
| `POST` | `/api/users/password/change/` | Trocar a senha com o código |
| `GET` | `/api/docs/` | Swagger com todas as rotas |

Nas rotas protegidas, envie o cabeçalho `Authorization: Token <seu_token>`.

## 🏗️ Arquitetura

O app guarda tudo no celular e só consulta a API para sugerir nomes de remédios. Por isso, se a API estiver fora do ar, o cadastro e os alarmes do app continuam funcionando. A API usa **SQLite** e é publicada no **Render** pelo `render.yaml`. O banco é recriado e o catálogo recarregado a cada deploy, então não depende de banco externo.

**Tecnologias:** Python 3.13 · Django 6 · Django REST Framework · `drf-spectacular` · `django-cors-headers` · `openpyxl` · Gunicorn · WhiteNoise

## 🚀 Como rodar (terminal)

**Pré-requisitos:** [Python 3.13](https://www.python.org/downloads/) instalado.

```bash
git clone https://github.com/Thiago-Vieira1/app-medcerto.git
cd app-medcerto
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz com uma chave qualquer:

```
SECRET_KEY=troque-esta-chave
```

```bash
python manage.py migrate
python manage.py seed_medications   # carrega os 6.012 remédios
python manage.py runserver          # abre em http://127.0.0.1:8000/api/docs/
```

**Testes:**

```bash
python manage.py test               # 26 testes
```

**Publicação no Render:** o `render.yaml` já configura tudo. No painel, preencha `CORS_ALLOWED_ORIGINS` com o endereço da versão web (sem `/` no final) e os dados do admin (`BOOTSTRAP_ADMIN_*`).


<sub>Projeto acadêmico, sem fins comerciais. O MedCerto não substitui orientação médica.</sub>
