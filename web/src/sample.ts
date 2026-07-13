export const SAMPLE_FEISHU = {
  code: 0,
  data: {
    items: [
      {
        block_id: 'page-demo',
        block_type: 1,
        page: {},
        children: ['heading-demo', 'text-demo', 'callout-demo', 'table-demo', 'image-demo', 'future-demo'],
      },
      {
        block_id: 'heading-demo',
        block_type: 3,
        heading1: {
          elements: [{ text_run: { content: 'Search reliability proposal' } }],
        },
      },
      {
        block_id: 'text-demo',
        block_type: 2,
        text: {
          elements: [
            { text_run: { content: 'The document model stays ' } },
            { text_run: { content: 'vendor-neutral', text_element_style: { bold: true } } },
            { text_run: { content: ' and can project into ' } },
            {
              mention_doc: {
                token: 'bookstack-target',
                obj_type: 22,
                url: 'https://example.invalid/bookstack',
              },
            },
            { text_run: { content: '.' } },
          ],
        },
      },
      {
        block_id: 'callout-demo',
        block_type: 19,
        callout: { background_color: 2, border_color: 2, emoji_id: 'bulb' },
        children: ['callout-text'],
      },
      {
        block_id: 'callout-text',
        block_type: 2,
        text: { elements: [{ text_run: { content: 'Unknown source blocks are preserved, never silently dropped.' } }] },
      },
      {
        block_id: 'table-demo',
        block_type: 31,
        table: {
          cells: ['cell-a', 'cell-b'],
          property: { row_size: 1, column_size: 2, column_width: [260, 260] },
        },
      },
      { block_id: 'cell-a', block_type: 32, table_cell: {}, children: ['cell-a-text'] },
      { block_id: 'cell-b', block_type: 32, table_cell: {}, children: ['cell-b-text'] },
      {
        block_id: 'cell-a-text',
        block_type: 2,
        text: { elements: [{ text_run: { content: 'Source' } }] },
      },
      {
        block_id: 'cell-b-text',
        block_type: 2,
        text: { elements: [{ text_run: { content: 'Projection' } }] },
      },
      {
        block_id: 'image-demo',
        block_type: 27,
        image: { token: 'synthetic-image-token', width: 1440, height: 900 },
      },
      {
        block_id: 'future-demo',
        block_type: 999,
        future_widget: { mode: 'source-preserved', value: 42 },
      },
    ],
  },
}

export const SAMPLE_TEXT = JSON.stringify(SAMPLE_FEISHU, null, 2)
