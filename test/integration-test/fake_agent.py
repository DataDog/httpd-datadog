# https://flask.palletsprojects.com/en/2.3.x/logging/
import msgpack
from flask import Flask, request, jsonify


# TODO: endpoint to create token
def make_agent():
    app = Flask(__name__)

    @app.route("/v0.4/traces", methods=["POST"])
    def handle_traces():
        trace = msgpack.unpackb(request.data)
        app.logger.info(trace)

        return jsonify({}), 200

    # Endpoints not handled
    @app.errorhandler(404)
    def not_found_error(error):
        return "", 404

    return app


if __name__ == "__main__":
    app = make_agent()
    app.run(host="0.0.0.0", port=8126)
