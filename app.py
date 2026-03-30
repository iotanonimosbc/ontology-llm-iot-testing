import json

from flask import Flask, render_template, request
from openai import OpenAI
import glob, yaml, os
import logging

# === CONFIGURAÇÃO FLASK ===
app = Flask(__name__)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# === CONFIGURAÇÃO OPENAI ===
client = OpenAI(
    api_key="")


def load_ontologies(path="./ontologias/"):
    ontologias = {}
    arquivos = glob.glob(os.path.join(path, "*.yaml")) + glob.glob(os.path.join(path, "*.yml"))

    for arquivo in arquivos:
        with open(arquivo, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            for k, v in data.items():
                ontologias[k] = v

    return ontologias


def build_form_fields(ontologia):
    campos = []
    valores_default = {}

    for campo, info in ontologia.get("properties", {}).items():

        if not isinstance(info, dict):
            continue

        if info.get("editable") is False:
            continue

        if info.get("type") == "object":
            continue

        campos.append({
            "Campo": campo,
            "Tipo": info.get("type", "string"),
            "Descrição": info.get("description", ""),
            "Opções": ",".join(map(str, info.get("allowedValues", info.get("items", []))))
        })

        valores_default[campo] = info.get("value", "")

    # Campo extra de modo de teste
    campos.append({
        "Campo": "hasTestMode",
        "Tipo": "string",
        "Descrição": "Modo de teste",
        "Opções": "Sensor Físico,Mock,Ambos"
    })
    valores_default["hasTestMode"] = "Mock"

    return campos, valores_default


def collect_form_answers(campos, request_form):
    respostas = {}
    for c in campos:
        respostas[c["Campo"]] = request_form.get(c["Campo"])
    return respostas


def build_prompt(sensor, ontologia, campos, respostas):
    modo_teste = respostas.get("hasTestMode", "Ambos")
    ontologia_json = json.dumps(ontologia, indent=2, ensure_ascii=False)

    prompt = f"""
Você é um agente GERADOR DE CÓDIGO de testes automatizados para sistemas IoT embarcados.

⚠️ REGRAS OBRIGATÓRIAS:
1. NÃO crie novos casos de teste.
2. USE EXCLUSIVAMENTE os casos de teste definidos na ontologia.
3. Cada item em `tests` DEVE gerar um teste em código.
4. Cada `steps` DEVE ser convertido em chamadas de função.
5. Cada `expected` DEVE virar asserções.
6. Preserve os IDs dos testes.
7. Respeite rigorosamente o campo `mode`.

### Sensor
Nome: {sensor}
Descrição: {ontologia.get("description", "N/A")}

### Modo de Execução
Modo selecionado: {modo_teste}

### Parâmetros configuráveis selecionados pelo usuário
"""

    for c in campos:
        prompt += f"- {c['Campo']}: {respostas.get(c['Campo'])}\n"

    prompt += f"""
### Ontologia COMPLETA (fonte única da verdade)
```json
{ontologia_json}"""

    logging.debug("Prompt enviado ao LLM:\n%s", prompt)

    return prompt


ontologias = load_ontologies()


def generate_code(prompt):
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Você gera código C++ para testes de sensores IoT."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return resposta.choices[0].message.content.strip()




@app.route("/")
def home():
    plataformas = {
        "Arduino": ["DS18B20", "DHT11", "InfraredMotionSensor", "HCSR04"],
        "Generico": ["DS18B20", "SensorGen2"]
    }
    return render_template("home.html", plataformas=plataformas)


@app.route("/sensor/<sensor>", methods=["GET", "POST"])
def formulario(sensor):
    ontologia = ontologias.get(sensor)
    if not ontologia:
        return f"Ontologia para {sensor} não encontrada.", 404

    campos, valores_default = build_form_fields(ontologia)

    if request.method == "POST":
        respostas = collect_form_answers(campos, request.form)
        prompt = build_prompt(sensor, ontologia, campos, respostas)
        codigo = generate_code(prompt)

        return render_template("resultado.html", codigo=codigo, ontologia=sensor)

    return render_template(
        "formulario.html",
        ontologia=sensor,
        campos=campos,
        valores_default=valores_default
    )

@app.route("/plataforma/<nome>")
def ver_plataforma(nome):
    sensores = []
    for sensor_nome, sensor_info in ontologias.items():
        plataforma = sensor_info.get("properties", {}) \
                                .get("hasPlatform", {}) \
                                .get("value")
        if plataforma == nome:
            sensores.append(sensor_nome)

    return render_template(
        "plataforma.html",
        nome=nome,
        sensores=sensores
    )



if __name__ == "__main__":
    app.run(debug=True)
