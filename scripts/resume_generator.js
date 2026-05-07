const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, LevelFormat, UnderlineType, ExternalHyperlink
} = require('docx');
const fs = require('fs');

// Get data from command line arguments
const data = JSON.parse(process.argv[2]);

// Color palette - light brown/warm grey (matching user preference)
const ACCENT = "8B7355";       // warm brown for name
const SECTION_LINE = "B8A898"; // light brown for section dividers
const DARK_TEXT = "2C2C2C";    // near-black for headings
const BODY_TEXT = "3D3D3D";    // body
const MUTED = "6B6B6B";        // company names, dates

const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

const font = "Calibri";

// Helper: section divider paragraph with bottom border
function sectionHeading(text) {
  return new Paragraph({
    spacing: { before: 220, after: 60 },
    border: {
      bottom: { style: BorderStyle.SINGLE, size: 6, color: SECTION_LINE, space: 4 }
    },
    children: [
      new TextRun({
        text: text.toUpperCase(),
        font,
        size: 20,
        bold: true,
        color: ACCENT,
        characterSpacing: 80
      })
    ]
  });
}

// Helper: bullet point
function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 20, after: 20 },
    children: [new TextRun({ text, font, size: 19, color: BODY_TEXT })]
  });
}

// Helper: job header row (role left, date right)
function jobHeader(role, company, date) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [6200, 3160],
    borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideH: noBorder, insideV: noBorder },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: noBorders,
            width: { size: 6200, type: WidthType.DXA },
            margins: { top: 0, bottom: 0, left: 0, right: 0 },
            children: [
              new Paragraph({
                spacing: { before: 120, after: 0 },
                children: [
                  new TextRun({ text: role, font, size: 20, bold: true, color: DARK_TEXT }),
                  new TextRun({ text: "  |  ", font, size: 20, color: MUTED }),
                  new TextRun({ text: company, font, size: 20, color: MUTED, italics: true })
                ]
              })
            ]
          }),
          new TableCell({
            borders: noBorders,
            width: { size: 3160, type: WidthType.DXA },
            margins: { top: 0, bottom: 0, left: 0, right: 0 },
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                spacing: { before: 120, after: 0 },
                children: [new TextRun({ text: date, font, size: 18, color: MUTED })]
              })
            ]
          })
        ]
      })
    ]
  });
}

// Helper: project header row
function projectHeader(name, link) {
  const children = [new TextRun({ text: name, font, size: 20, bold: true, color: DARK_TEXT })];
  if (link) {
    children.push(new TextRun({ text: "  —  ", font, size: 19, color: MUTED }));
    children.push(
      new ExternalHyperlink({
        link,
        children: [new TextRun({ text: link, font, size: 18, color: "7B6B55", underline: { type: UnderlineType.SINGLE } })]
      })
    );
  }
  return new Paragraph({
    spacing: { before: 120, after: 20 },
    children
  });
}

function spacer(pts = 80) {
  return new Paragraph({ spacing: { before: 0, after: pts }, children: [new TextRun("")] });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0,
          format: LevelFormat.BULLET,
          text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 440, hanging: 280 } } }
        }]
      }
    ]
  },
  styles: {
    default: {
      document: { run: { font, size: 20, color: BODY_TEXT } }
    }
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 900, right: 1080, bottom: 900, left: 1080 }
      }
    },
    children: [
      // NAME
      new Paragraph({
        alignment: AlignmentType.LEFT,
        spacing: { before: 0, after: 40 },
        children: [
          new TextRun({ text: data.full_name.toUpperCase(), font, size: 52, bold: true, color: ACCENT })
        ]
      }),

      // TAGLINE
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [
          new TextRun({ text: data.tagline, font, size: 22, color: MUTED })
        ]
      }),

      // CONTACT ROW
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideH: noBorder, insideV: noBorder },
        rows: [
          new TableRow({
            children: [
                new TableCell({
                    borders: noBorders,
                    children: [
                        new Paragraph({
                            spacing: { before: 0, after: 80 },
                            children: [
                                new TextRun({ text: `${data.email} | ${data.phone} | ${data.location}`, font, size: 17, color: MUTED })
                            ]
                        })
                    ]
                })
            ]
          }),
          new TableRow({
            children: [
                new TableCell({
                    borders: noBorders,
                    children: [
                        new Paragraph({
                            spacing: { before: 0, after: 80 },
                            children: [
                                data.linkedin ? new ExternalHyperlink({ link: data.linkedin, children: [new TextRun({ text: "LinkedIn", font, size: 17, color: "7B6B55", underline: { type: UnderlineType.SINGLE } })] }) : new TextRun(""),
                                data.linkedin && data.github ? new TextRun({ text: " | ", font, size: 17, color: MUTED }) : new TextRun(""),
                                data.github ? new ExternalHyperlink({ link: data.github, children: [new TextRun({ text: "GitHub", font, size: 17, color: "7B6B55", underline: { type: UnderlineType.SINGLE } })] }) : new TextRun(""),
                                (data.linkedin || data.github) && data.portfolio ? new TextRun({ text: " | ", font, size: 17, color: MUTED }) : new TextRun(""),
                                data.portfolio ? new ExternalHyperlink({ link: data.portfolio, children: [new TextRun({ text: "Portfolio", font, size: 17, color: "7B6B55", underline: { type: UnderlineType.SINGLE } })] }) : new TextRun(""),
                            ]
                        })
                    ]
                })
            ]
          })
        ]
      }),

      spacer(60),

      // SUMMARY
      sectionHeading("Professional Summary"),
      new Paragraph({
        spacing: { before: 80, after: 80 },
        children: [
          new TextRun({
            text: data.summary,
            font, size: 19, color: BODY_TEXT
          })
        ]
      }),

      spacer(40),

      // TECHNICAL SKILLS
      sectionHeading("Technical Skills"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1600, 7760],
        borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideH: noBorder, insideV: noBorder },
        rows: data.technical_skills.map(s => new TableRow({
            children: [
              new TableCell({
                borders: noBorders,
                width: { size: 1600, type: WidthType.DXA },
                margins: { top: 40, bottom: 40, left: 0, right: 120 },
                children: [new Paragraph({
                  spacing: { before: 40, after: 40 },
                  children: [new TextRun({ text: s.category, font, size: 19, bold: true, color: DARK_TEXT })]
                })]
              }),
              new TableCell({
                borders: noBorders,
                width: { size: 7760, type: WidthType.DXA },
                margins: { top: 40, bottom: 40, left: 0, right: 0 },
                children: [new Paragraph({
                  spacing: { before: 40, after: 40 },
                  children: [new TextRun({ text: s.skills, font, size: 19, color: BODY_TEXT })]
                })]
              })
            ]
          }))
      }),

      spacer(40),

      // EXPERIENCE
      sectionHeading("Professional Experience"),
      ...data.experiences.flatMap(exp => [
        jobHeader(exp.role, exp.company, exp.dates),
        ...exp.bullets.map(b => bullet(b)),
        spacer(60)
      ]),

      spacer(40),

      // PROJECTS
      sectionHeading("Selected Projects"),
      ...data.projects.flatMap(p => [
        projectHeader(p.name, p.link),
        p.stack ? new Paragraph({
            spacing: { before: 0, after: 20 },
            children: [new TextRun({ text: `Stack: ${p.stack}`, font, size: 18, color: MUTED, italics: true })]
          }) : spacer(0),
        ...p.bullets.map(b => bullet(b)),
        spacer(60)
      ]),

      spacer(40),

      // CERTIFICATIONS
      sectionHeading("Certifications & Training"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [5200, 4160],
        borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideH: noBorder, insideV: noBorder },
        rows: data.certifications.map(c => new TableRow({
            children: [
              new TableCell({
                borders: noBorders,
                width: { size: 5200, type: WidthType.DXA },
                margins: { top: 40, bottom: 40, left: 0, right: 0 },
                children: [new Paragraph({
                  spacing: { before: 40, after: 40 },
                  children: [new TextRun({ text: c.name, font, size: 19, bold: true, color: DARK_TEXT })]
                })]
              }),
              new TableCell({
                borders: noBorders,
                width: { size: 4160, type: WidthType.DXA },
                margins: { top: 40, bottom: 40, left: 0, right: 0 },
                children: [new Paragraph({
                  alignment: AlignmentType.RIGHT,
                  spacing: { before: 40, after: 40 },
                  children: [new TextRun({ text: `${c.issuer} · ${c.date}`, font, size: 18, color: MUTED })]
                })]
              })
            ]
          }))
      }),

      spacer(40),

      // EDUCATION
      sectionHeading("Education"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [7000, 2360],
        borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder, insideH: noBorder, insideV: noBorder },
        rows: data.education.map(e => new TableRow({
            children: [
              new TableCell({
                borders: noBorders,
                width: { size: 7000, type: WidthType.DXA },
                margins: { top: 60, bottom: 20, left: 0, right: 0 },
                children: [
                  new Paragraph({
                    spacing: { before: 60, after: 20 },
                    children: [
                      new TextRun({ text: e.degree, font, size: 20, bold: true, color: DARK_TEXT }),
                    ]
                  }),
                  new Paragraph({
                    spacing: { before: 0, after: 40 },
                    children: [
                      new TextRun({ text: `${e.institution} · ${e.location}`, font, size: 19, color: MUTED })
                    ]
                  })
                ]
              }),
              new TableCell({
                borders: noBorders,
                width: { size: 2360, type: WidthType.DXA },
                margins: { top: 60, bottom: 20, left: 0, right: 0 },
                children: [new Paragraph({
                  alignment: AlignmentType.RIGHT,
                  spacing: { before: 60, after: 20 },
                  children: [new TextRun({ text: e.dates, font, size: 19, color: MUTED })]
                })]
              })
            ]
          }))
      }),

      spacer(100),
      // BRANDING
      data.include_branding ? new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
            new TextRun({ text: "Generated by Huntly", font, size: 16, color: MUTED, italics: true })
        ]
      }) : spacer(0),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  process.stdout.write(buf);
});
