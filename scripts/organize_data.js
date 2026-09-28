const fs = require('fs');
const path = require('path');

const dataDir = path.resolve(__dirname, '..', 'data');
const citypairDir = path.join(dataDir, 'dgca_citypair');
const traffic2025Dir = path.join(dataDir, 'dgca_traffic_2025');
const traffic2026Dir = path.join(dataDir, 'dgca_traffic_2026');

[citypairDir, traffic2025Dir, traffic2026Dir].forEach(d => {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
});

const monthMap = {
  'JANUARY': '01',
  'FEBRUARY': '02',
  'MARCH': '03',
  'APRIL': '04',
  'MAY': '05',
  'JUNE': '06',
  'JULY': '07',
  'AUGUST': '08',
  'SEPTEMBER': '09',
  'OCTOBER': '10',
  'NOVEMBER': '11',
  'DECEMBER': '12'
};

const map25 = {
  'Air India25.xlsx': 'air_india_2025.xlsx',
  'air india express25.xlsx': 'air_india_express_2025.xlsx',
  'akasa air 25.xlsx': 'akasa_air_2025.xlsx',
  'alliance air25.xlsx': 'alliance_air_2025.xlsx',
  'bluedart25.xlsx': 'bluedart_cargo_2025.xlsx',
  'fly91 25.xlsx': 'fly91_2025.xlsx',
  'Flybig25.xlsx': 'flybig_2025.xlsx',
  'india one air25.xlsx': 'india_one_air_2025.xlsx',
  'indigo25.xlsx': 'indigo_2025.xlsx',
  'quikjetcargo25.xlsx': 'quikjet_cargo_2025.xlsx',
  'spicejet25.xlsx': 'spicejet_2025.xlsx',
  'star air25.xlsx': 'star_air_2025.xlsx',
  'totaldom25.xlsx': 'total_dom_2025.xlsx',
  'totalint25.xlsx': 'total_int_2025.xlsx'
};

const map26 = {
  'star air26.xlsx': 'star_air_2026.xlsx',
  'totaldom26.xlsx': 'total_dom_2026.xlsx',
  'totalint26.xlsx': 'total_int_2026.xlsx'
};

const files = fs.readdirSync(dataDir);

files.forEach(file => {
  const filePath = path.join(dataDir, file);
  if (!fs.statSync(filePath).isFile()) return;

  // Check duplicate
  if (file.includes('(1)')) {
    fs.unlinkSync(filePath);
    console.log('Removed duplicate:', file);
    return;
  }

  // Citypair files
  if (file.startsWith('DOM CITYPAIR DATA')) {
    const upper = file.toUpperCase();
    let monthNum = null;
    for (const [mName, mCode] of Object.entries(monthMap)) {
      if (upper.includes(mName)) {
        monthNum = mCode;
        break;
      }
    }

    if (monthNum) {
      const year = file.includes('2025') ? '2025' : (file.includes('2026') ? '2026' : null);
      if (year) {
        const destName = `citypair_${year}_${monthNum}.xlsx`;
        fs.renameSync(filePath, path.join(citypairDir, destName));
        console.log(`Moved citypair: ${file} -> dgca_citypair/${destName}`);
        return;
      }
    }
  }

  // Traffic 2025
  if (map25[file]) {
    fs.renameSync(filePath, path.join(traffic2025Dir, map25[file]));
    console.log(`Moved 2025 traffic: ${file} -> dgca_traffic_2025/${map25[file]}`);
    return;
  }

  // Traffic 2026
  if (map26[file]) {
    fs.renameSync(filePath, path.join(traffic2026Dir, map26[file]));
    console.log(`Moved 2026 traffic: ${file} -> dgca_traffic_2026/${map26[file]}`);
    return;
  }
});

console.log('\n--- Done organizing! ---');
