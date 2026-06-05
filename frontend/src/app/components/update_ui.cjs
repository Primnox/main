const fs = require('fs');
const path = require('path');

const files = [
  'SummaryViews.tsx',
  'SettingsView.tsx',
  'OnboardingView.tsx'
];

files.forEach(file => {
  const filePath = path.join('C:\\Users\\aniketh\\Projects\\Primnox\\frontend\\src\\app\\components', file);
  if (!fs.existsSync(filePath)) return;
  
  let content = fs.readFileSync(filePath, 'utf8');

  // 1. Standardize Headings (h1, h2, h3)
  content = content.replace(/<(h[1-3])(.*?)className=["']([^"']+)["']/g, (match, tag, beforeClass, classList) => {
    let classes = classList.split(/\s+/).filter(c => 
      !c.includes('font-bold') && 
      !c.includes('tracking-tight') && 
      !c.includes('tracking-tighter') &&
      !c.includes('lowercase') && 
      !c.includes('italic') &&
      !c.includes('tracking-wide')
    );
    
    // Add the new standard classes
    classes.unshift('font-bold', 'lowercase', 'italic', 'tracking-wide');
    
    return `<${tag}${beforeClass}className="${classes.join(' ')}"`;
  });

  // 2. Add Micro-animations to Buttons
  content = content.replace(/<button(.*?)className=["']([^"']+)["']/g, (match, beforeClass, classList) => {
    let classes = classList.split(/\s+/).filter(c => 
      !c.startsWith('transition-') && 
      !c.startsWith('duration-') &&
      !c.startsWith('ease-') &&
      !c.startsWith('active:scale-') &&
      c !== 'transition'
    );
    
    classes.push('transition-all', 'duration-300', 'ease-out', 'active:scale-95');
    
    return `<button${beforeClass}className="${classes.join(' ')}"`;
  });

  // 3. Add Micro-animations to Labels with cursor-pointer (Toggles)
  content = content.replace(/<label(.*?)className=["']([^"']*cursor-pointer[^"']*)["']/g, (match, beforeClass, classList) => {
    let classes = classList.split(/\s+/).filter(c => 
      !c.startsWith('transition-') && 
      !c.startsWith('duration-') &&
      !c.startsWith('ease-') &&
      !c.startsWith('active:scale-') &&
      c !== 'transition'
    );
    
    classes.push('transition-all', 'duration-300', 'ease-out', 'active:scale-95');
    
    return `<label${beforeClass}className="${classes.join(' ')}"`;
  });

  // 4. Add Micro-animations to Clickable Divs (Cards)
  content = content.replace(/<div([^>]+onClick=[^>]+className=["'][^"']+["'][^>]*)>/g, (match, attributes) => {
    return '<div' + attributes.replace(/className=["']([^"']+)["']/, (cMatch, classList) => {
      let classes = classList.split(/\s+/).filter(c => 
        !c.startsWith('transition-') && 
        !c.startsWith('duration-') &&
        !c.startsWith('ease-') &&
        !c.startsWith('active:scale-') &&
        c !== 'transition'
      );
      classes.push('transition-all', 'duration-300', 'ease-out', 'active:scale-95');
      return `className="${classes.join(' ')}"`;
    }) + '>';
  });

  // 5. Add Micro-animations to Clickable 'a' tags
  content = content.replace(/<a([^>]+onClick=[^>]+className=["'][^"']+["'][^>]*)>/g, (match, attributes) => {
      return '<a' + attributes.replace(/className=["']([^"']+)["']/, (cMatch, classList) => {
        let classes = classList.split(/\s+/).filter(c => 
          !c.startsWith('transition-') && 
          !c.startsWith('duration-') &&
          !c.startsWith('ease-') &&
          !c.startsWith('active:scale-') &&
          c !== 'transition'
        );
        classes.push('transition-all', 'duration-300', 'ease-out', 'active:scale-95');
        return `className="${classes.join(' ')}"`;
      }) + '>';
  });

  // One special case in SettingsView.tsx where className uses template literals
  // className={`w-full text-left ... border
  // ${isActive ...}`}
  // We can just append the classes inside the fixed part of the template literal
  if (file === 'SettingsView.tsx') {
      content = content.replace(/className=\{`([^`]+)transition-all([^`]*)`\}/g, (match, before, after) => {
          // Check if it's already got active:scale-95
          if (match.includes('active:scale-95')) return match;
          
          return `className={\`${before}transition-all duration-300 ease-out active:scale-95${after}\`}`;
      });
  }

  fs.writeFileSync(filePath, content, 'utf8');
  console.log(`Updated ${file}`);
});
