from flask import Flask, render_template, request, jsonify, Response
import asyncio
import threading
import json
import time
from queue import Queue
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store active processes
active_processes = {}

# Import your existing functions
from ip_changer import process_phone_number

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_process():
    data = request.json
    phone_number = data.get('phoneNumber')
    
    if not phone_number or not phone_number.isdigit() or len(phone_number) != 10:
        return jsonify({'error': 'Invalid phone number'}), 400
    
    # Create unique process ID
    process_id = f"process_{int(time.time())}"
    
    # Create queue for this process
    result_queue = Queue()
    active_processes[process_id] = {
        'queue': result_queue,
        'status': 'running'
    }
    
    # Start background thread
    thread = threading.Thread(
        target=run_async_process,
        args=(process_id, phone_number, result_queue)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'processId': process_id})

def run_async_process(process_id, phone_number, queue):
    """Run the async process in a separate thread"""
    try:
        # Create new event loop for the thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the main function
        result = loop.run_until_complete(
            process_phone_number(phone_number, queue)
        )
        
        # Send completion
        queue.put({
            'type': 'complete',
            'data': result
        })
        
    except Exception as e:
        logger.error(f"Error in process {process_id}: {str(e)}")
        queue.put({
            'type': 'error',
            'message': str(e)
        })
    finally:
        active_processes[process_id]['status'] = 'completed'

@app.route('/stream/<process_id>')
def stream(process_id):
    """SSE stream for real-time updates"""
    if process_id not in active_processes:
        return jsonify({'error': 'Process not found'}), 404
    
    def generate():
        queue = active_processes[process_id]['queue']
        
        while True:
            try:
                # Get update from queue (timeout to check if process still alive)
                update = queue.get(timeout=1)
                yield f"data: {json.dumps(update)}\n\n"
                
                if update.get('type') == 'complete' or update.get('type') == 'error':
                    break
                    
            except:
                # Check if process is still alive
                if active_processes[process_id]['status'] == 'completed':
                    break
                continue
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/stop/<process_id>', methods=['POST'])
def stop_process(process_id):
    """Stop a running process"""
    if process_id in active_processes:
        active_processes[process_id]['status'] = 'stopping'
        return jsonify({'success': True})
    return jsonify({'error': 'Process not found'}), 404

# Cleanup old processes (optional)
@app.before_request
def cleanup_old_processes():
    """Remove processes older than 1 hour"""
    current_time = time.time()
    to_delete = []
    
    for pid, info in active_processes.items():
        # You might want to store start time in the process info
        pass
    
    for pid in to_delete:
        del active_processes[pid]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)