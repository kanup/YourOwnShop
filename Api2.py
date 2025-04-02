from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        # Process the POST data (for example, from a submitted form)
        posted_data = request.form.get('data', 'No data provided')
        return jsonify({
            'status': 'success',
            'message': f"You posted: {posted_data}"
        })
    else:
        # For GET requests, return some sample data
        data = {
            'status': 'success',
            'data': 'Here is the data you requested'
        }
        return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
