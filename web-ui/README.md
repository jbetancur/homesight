# HomeSight Web UI

Modern React dashboard for HomeSight home monitoring system.

## Tech Stack

- **React 18** + **TypeScript**
- **Vite** - Fast build tool  
- **Tailwind CSS** - Utility-first styling
- **Lucide React** - Beautiful icons

## Development

```bash
# Install dependencies
npm install

# Start dev server (http://localhost:5173)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Features

- ✅ **Real-time updates** - Auto-refresh every 5s
- ✅ **Device management** - View all connected devices  
- ✅ **Incident monitoring** - Track active alerts
- ✅ **Discovery** - See newly discovered devices
- ✅ **Responsive design** - Works on mobile & desktop

## API Connection

The UI connects to the HomeSight API at `http://localhost:8080/api`.

Make sure the HomeSight daemon is running:
```bash
cd ..
./scripts/homesight.sh start
```

## Deployment

### Production Build
```bash
npm run build
# Output: dist/
```

### Serve with Nginx
```nginx
server {
    listen 80;
    server_name homesight.local;
    root /var/www/homesight;
    index index.html;

    # API proxy
    location /api {
        proxy_pass http://localhost:8080;
    }

    # React routes
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## Future Enhancements

- [ ] Device control actions
- [ ] Charts/graphs for metrics  
- [ ] Settings page
- [ ] Dark mode
- [ ] Notifications
- [ ] Mobile app (React Native)
