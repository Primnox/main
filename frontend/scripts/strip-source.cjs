const fs = require('fs');
const path = require('path');

// Remove source maps
const distDir = path.join(__dirname, '../dist');
function removeSourceMaps(dir) {
  if (!fs.existsSync(dir)) return;
  fs.readdirSync(dir).forEach(file => {
    const full = path.join(dir, file);
    if (fs.statSync(full).isDirectory()) {
      removeSourceMaps(full);
    } else if (file.endsWith('.map')) {
      fs.unlinkSync(full);
      console.log('Removed:', full);
    }
  });
}
removeSourceMaps(distDir);
console.log('Source maps removed.');
