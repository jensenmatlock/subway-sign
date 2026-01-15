import express from 'express';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import apiRoutes from './routes/api.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(
  readFileSync(join(__dirname, '..', 'config.json'), 'utf-8')
);

const app = express();

// Middleware
app.use(express.json());

// API routes
app.use('/api', apiRoutes);

// Root endpoint with API documentation
app.get('/', (req, res) => {
  res.json({
    name: 'NYC Subway Sign API',
    version: '1.0.0',
    endpoints: {
      '/api/arrivals': 'Get formatted arrivals for display (main endpoint)',
      '/api/arrivals/raw': 'Get raw arrival data for debugging',
      '/api/stations?search=<term>': 'Search for stations by name',
      '/api/station/:id': 'Get station name by ID',
      '/api/config': 'Get current display configuration',
      '/api/health': 'Health check with feed status'
    },
    config: {
      direction: config.direction,
      rows: Object.entries(config.layout).map(([key, row]) => ({
        row: key,
        lines: row.lines.join(', '),
        station: row.station
      }))
    }
  });
});

const port = config.server.port;
app.listen(port, () => {
  console.log(`
╔════════════════════════════════════════════════════════╗
║           NYC Subway Sign API Server                    ║
╠════════════════════════════════════════════════════════╣
║  Server running at: http://localhost:${port}              ║
║                                                         ║
║  Endpoints:                                             ║
║    GET /api/arrivals     - Arrivals for display         ║
║    GET /api/arrivals/raw - Raw data (debug)             ║
║    GET /api/health       - Health check                 ║
║    GET /api/config       - Current configuration        ║
║                                                         ║
║  Configuration:                                         ║
║    Direction: ${config.direction === 'S' ? 'Downtown (Southbound)' : 'Uptown (Northbound)'}              ║
║    Row 1: ${config.layout.row1.lines.join(', ')} from ${config.stations[config.layout.row1.station].name}
║    Row 2: ${config.layout.row2.lines.join(', ')} from ${config.stations[config.layout.row2.station].name}
║    Row 3: ${config.layout.row3.lines.join(', ')} from ${config.stations[config.layout.row3.station].name}
╚════════════════════════════════════════════════════════╝
  `);
});
