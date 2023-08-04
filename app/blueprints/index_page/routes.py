from flask import Blueprint, make_response, render_template, current_app, Response, request

import openai
import re
import redis
import json

blueprint: Blueprint = Blueprint(
    'index',
    __name__,
    template_folder='templates',
    static_folder='static'
)


@blueprint.route("/", methods=["get"])
def index_route() -> Response:
    return make_response(
        render_template(
            "index.jinja2",
        )
    )


@blueprint.route("/lookup", methods=["get"])
def lookup_route() -> Response:
    # Extract the name
    lookup_name = request.args.get("name")

    # Verify length
    if len(lookup_name) > 5:
        return Response("Name too long (>10 chars)", status=400)

    # Verify whether only Chinese characters are present
    pattern = re.compile(r"[^\u4e00-\u9fff\uff00-\uffef\u3000-\u303f\ufb00-\ufb4f]")
    if re.search(pattern, lookup_name) is not None:
        return Response("Non-Chinese characters detected", status=400)

    # Perform a lookup in redis
    rds = redis.Redis(host=current_app.config['REDIS_HOST'],
                      port=current_app.config['REDIS_PORT'],
                      password=current_app.config['REDIS_PWD'],
                      ssl=current_app.config['REDIS_SSL'],
                      decode_responses=True)
    cached_name = rds.hgetall(lookup_name)

    # Increment the counter
    rds.incr(f"{lookup_name}_counter", 1)

    # If we have it in the cache, return it directly
    if cached_name:
        return make_response((cached_name, 200))

    # Call OpenAI to fetch
    else:
        openai.organization = current_app.config["OPENAI_ORGANIZATION"]
        openai.api_key = current_app.config["OPENAI_API_KEY"]

        try:
            response = openai.ChatCompletion.create(
                model=current_app.config["OPENAI_TARGET_MODEL"],
                messages=[
                    {"role": "system", "content": current_app.config["GPT_SYSTEM_PROMPT"]},
                    {"role": "user", "content": lookup_name},
                ],
                temperature=0,
            )

            gpt_resp = json.loads(response['choices'][0]["message"]["content"])

            # Cache it in redis
            rds.hset(lookup_name, mapping=gpt_resp)

            # Return the response
            return make_response((gpt_resp, 200))

        except openai.error.OpenAIError as e:
            print(e)
            return Response("OpenAI API error, please try again later.", status=500)
