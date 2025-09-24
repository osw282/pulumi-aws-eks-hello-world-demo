from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/api/hello')
def hello_api():
    return {'message': 'Hello World from API!'}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
