import os
import json
import pandas as pd
import markdown
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import main
from tools import visualize_data_map
import ee
from modules import timeseries_generator
from flask import Response

app = Flask(__name__)

# Initialize Earth Engine (required for cube generation)
try:
    ee.Initialize()
    print("✓ Earth Engine initialized")
except Exception as e:
    print(f"⚠ Earth Engine initialization failed: {e}")
    print("  Run 'earthengine authenticate' if needed")

# Ensure output directory exists
os.makedirs('output', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/rois', methods=['GET'])
def list_rois():
    rois = []
    if os.path.exists('rois'):
        for f in os.listdir('rois'):
            if f.endswith('.json'):
                rois.append(f.replace('.json', ''))
    return jsonify(rois)

@app.route('/rois/<name>', methods=['GET'])
def get_roi(name):
    path = os.path.join('rois', f"{name}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({'error': 'ROI not found'}), 404

@app.route('/rois', methods=['POST'])
def save_roi():
    data = request.json
    name = data.get('name')
    geometry = data.get('geometry')
    
    if not name or not geometry:
        return jsonify({'success': False, 'error': 'Missing name or geometry'})
        
    os.makedirs('rois', exist_ok=True)
    path = os.path.join('rois', f"{name}.json")
    
    with open(path, 'w') as f:
        json.dump(geometry, f, indent=4)
        
    return jsonify({'success': True})

# Global progress store
analysis_progress = {}

@app.route('/progress/<project_name>')
def get_progress(project_name):
    return jsonify(analysis_progress.get(project_name, {'status': 'idle', 'percent': 0}))

@app.route('/run_analysis', methods=['POST'])
def run_analysis():
    try:
        data = request.json
        project_name = data.get('project_name', 'default')
        geometry = data.get('geometry')
        
        if not geometry or 'coordinates' not in geometry:
            return jsonify({'success': False, 'error': 'Invalid geometry'})
            
        roi_coords = geometry['coordinates']
        t1_start = data.get('t1_start', '2024-06-01')
        t1_end = data.get('t1_end', '2024-07-15')
        t2_start = data.get('t2_start', '2024-08-01')
        t2_end = data.get('t2_end', '2024-09-15')
        
        # Initialize progress
        analysis_progress[project_name] = {'status': 'Starting...', 'percent': 5}
        
        def update_progress(msg):
            current = analysis_progress.get(project_name, {'percent': 0})
            new_percent = min(current['percent'] + 10, 95)
            analysis_progress[project_name] = {'status': msg, 'percent': new_percent}
        
        # Run Pipeline
        result = main.run_pipeline(
            roi_coords=roi_coords, 
            project_name=project_name, 
            t1_start=t1_start,
            t1_end=t1_end,
            t2_start=t2_start,
            t2_end=t2_end,
            progress_callback=update_progress
        )
        
        if result:
            # Generate Map
            csv_path = result['csv_path']
            output_dir = result['output_dir']
            map_path = os.path.join(output_dir, f'Map_{project_name}.html')
            
            visualize_data_map.create_verification_map(csv_path, map_path)
            
            analysis_progress[project_name] = {'status': 'Complete', 'percent': 100}
            return jsonify({'success': True, 'project_name': project_name})
        else:
            analysis_progress[project_name] = {'status': 'Failed', 'percent': 0}
            return jsonify({'success': False, 'error': 'Pipeline failed'})
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dashboard/<project_name>')
def dashboard(project_name):
    output_dir = os.path.join('output', project_name)
    csv_path = os.path.join(output_dir, f'SmartHarvest_{project_name}.csv')
    report_path = os.path.join(output_dir, f'Report_{project_name}.md')
    metadata_path = os.path.join(output_dir, f'metadata_{project_name}.json')
    
    # Read Metadata Stats
    stats = []
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            meta_list = json.load(f)
            for item in meta_list:
                if 'source' in item:
                    if item['source'] == 'ROI Stats':
                        stats.append({'label': "Area (ha)", 'value': f"{item['area_ha']:.2f}"})
                        stats.append({'label': "Area (m²)", 'value': f"{item['area_sqm']:.0f}"})
                    elif item['source'] == 'SRTM':
                        stats.append({'label': "Topography", 'value': "Static (SRTM)"})
                    elif 'ERA5' in item['source']:
                        stats.append({'label': "Climate Data", 'value': "Hourly (ERA5)"})
                    elif 'image_count' in item:
                        stats.append({'label': f"{item['source']} Images", 'value': str(item['image_count'])})
    
    # Fallback if no metadata
    if not stats and os.path.exists(csv_path):
         df = pd.read_csv(csv_path)
         stats.append({'label': 'Total Pixels', 'value': str(len(df))})
         
    # Read Report
    report_html = "<p>Report not found.</p>"
    if os.path.exists(report_path):
        with open(report_path, 'r') as f:
            md_text = f.read()
            report_html = markdown.markdown(md_text, extensions=['tables'])
            
    # Generate Analysis Charts
    from modules import analysis
    charts = analysis.generate_analysis_dashboard(project_name, output_dir)
            
    return render_template('dashboard.html', 
                           project_name=project_name, 
                           stats=stats, 
                           report_html=report_html,
                           charts=charts)

@app.route('/map/<project_name>')
def get_map(project_name):
    output_dir = os.path.join('output', project_name)
    map_filename = f'Map_{project_name}.html'
    return send_from_directory(output_dir, map_filename)

@app.route('/download/<project_name>')
def download_csv(project_name):
    """Serves the static spatial snapshot cube."""
    output_dir = os.path.join('output', project_name)
    csv_filename = f'SmartHarvest_{project_name}.csv'
    return send_from_directory(output_dir, csv_filename, as_attachment=True)

@app.route('/generate_ts_dataset', methods=['POST'])
def generate_ts_dataset():
    data = request.json
    project_name = data.get('project_name')
    start_date = data.get('start_date') # DD/MM
    end_date = data.get('end_date')     # DD/MM
    years = data.get('years')           # ['2023', '2024']
    
    output_dir = os.path.join('output', project_name)
    roi_path = os.path.join(output_dir, 'roi.json')
    
    if not os.path.exists(roi_path):
        return jsonify({'error': 'ROI not found. Please run baseline analysis first.'}), 404
        
    with open(roi_path, 'r') as f:
        roi_geojson = json.load(f)
        roi = ee.Geometry(roi_geojson)

    def stream_logic():
        for update in timeseries_generator.generate_ts_dataset_v2(roi, start_date, end_date, years, project_name, output_dir):
            yield f"data: {json.dumps(update)}\n\n"

    return Response(stream_logic(), mimetype='text/event-stream')

@app.route('/download_dataset/<project_name>/<filename>')
def download_dataset(project_name, filename):
    output_dir = os.path.join('output', project_name)
    return send_from_directory(output_dir, filename, as_attachment=True)

if __name__ == '__main__':
    print("🍇 SmartHarvest Web App Started")
    print("👉 Open: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
